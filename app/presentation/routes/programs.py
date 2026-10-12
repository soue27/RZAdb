import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi import File as FastAPIFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.application.files.service import FileService
from app.application.objects.exceptions import (
    ObjectAccessDeniedError,
    ObjectNotFoundError,
)
from app.application.objects.service import ObjectService
from app.application.programs.service import ProgramService
from app.application.tasks.service import TaskService
from app.application.tree.service import TreeService
from app.domain.enums import DocumentStatus, ProgramType, UserRole
from app.domain.user import User
from app.presentation.auth.dependencies import get_current_user
from app.presentation.dependencies.services import (
    get_file_service,
    get_object_service,
    get_program_service,
    get_task_service,
    get_tree_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/objects",
    tags=["objects"],
)

templates = Jinja2Templates(
    directory="app/presentation/templates",
)


async def _render_urza_programs(
    request: Request,
    urza_id: UUID,
    current_user: User,
    program_service: ProgramService,
    task_service: TaskService,
    tree_service: TreeService,
):
    programs = await program_service.get_by_urza(
        user_id=current_user.id,
        urza_id=urza_id,
    )

    program_actions = {
        program.id: await program_service.get_available_actions(
            user_id=current_user.id,
            program=program,
        )
        for program in programs
    }

    can_issue_task = await task_service.can_issue_task(
        actor_id=current_user.id,
        urza_id=urza_id,
    )

    context = {
        "urza_id": urza_id,
        "programs": programs,
        "program_actions": program_actions,
        "can_issue_task": can_issue_task,
        "can_create_program": current_user.role in {
            UserRole.MANAGER,
            UserRole.ENGINEER,
            UserRole.ADMIN,
            UserRole.SUPERADMIN,
        },
    }

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="objects/urza_programs.html",
            context=context,
        )

    tree = await tree_service.get_tree(user_id=current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_programs_page.html",
        context={
            **context,
            "current_user": current_user,
            "tree": tree,
            "content_template": "objects/urza_programs.html",
        },
    )


@router.get("/urza/{urza_id}/programs")
async def get_urza_programs(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект не найден.",
        ) from exc

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
        task_service=task_service,
        tree_service=tree_service,
    )



@router.get("/urza/{urza_id}/programs/new")
async def get_new_urza_program_form(
    request: Request,
    urza_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],
    task_id: UUID | None = None,
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект не найден.",
        ) from exc

    if current_user.role not in {
        UserRole.MANAGER,
        UserRole.ENGINEER,
        UserRole.ADMIN,
        UserRole.SUPERADMIN,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Создавать программы с текущей ролью запрещено.",
        )

    if task_id is not None:
        try:
            await program_service.validate_task_for_result(
                user_id=current_user.id,
                urza_id=urza_id,
                task_id=task_id,
            )
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    context = {
        "urza_id": urza_id,
        "program_types": list(ProgramType),
        "task_id": task_id,
        "creation_status_notice": (
            "После сохранения программа сразу получит статус «Утверждена»."
            if current_user.role is UserRole.MANAGER
            else (
                "После сохранения программа будет создана в статусе "
                "«Черновик». После подготовки её можно направить "
                "на согласование."
            )
        ),
    }

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="objects/urza_program_form.html",
            context=context,
        )

    tree = await tree_service.get_tree(user_id=current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_programs_page.html",
        context={
            **context,
            "current_user": current_user,
            "tree": tree,
            "content_template": "objects/urza_program_form.html",
        },
    )



@router.get("/urza/{urza_id}/programs/{program_id}/edit")
async def get_edit_urza_program_form(
    request: Request,
    urza_id: UUID,
    program_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
        program = await program_service.get_by_id(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект не найден.",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if program is None or program.urza_id != urza_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Программа не найдена.",
        )

    if program.status is not DocumentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Редактировать можно только черновик.",
        )

    context = {
        "urza_id": urza_id,
        "program_types": list(ProgramType),
        "task_id": program.task_id,
        "program": program,
        "is_edit": True,
    }

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="objects/urza_program_form.html",
            context=context,
        )

    tree = await tree_service.get_tree(user_id=current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="objects/urza_programs_page.html",
        context={
            **context,
            "current_user": current_user,
            "tree": tree,
            "content_template": "objects/urza_program_form.html",
        },
    )



@router.post("/urza/{urza_id}/programs")
async def create_urza_program(
    request: Request,
    urza_id: UUID,
    program_type: Annotated[ProgramType, Form()],
    program_number: Annotated[str, Form()],
    scan_file: Annotated[UploadFile, FastAPIFile()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],
    task_id: Annotated[UUID | None, Form()] = None,
    editable_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
):
    # Проверяем доступ к URZA.
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект не найден.",
        ) from exc

    # Проверяем номер до загрузки файлов.
    normalized_program_number = program_number.strip()

    if not normalized_program_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Номер программы не может быть пустым.",
        )

    if len(normalized_program_number) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Номер программы не должен превышать 255 символов.",
        )

    # Проверяем допустимость задания, если оно указано.
    if task_id is not None:
        try:
            await program_service.validate_task_for_result(
                user_id=current_user.id,
                urza_id=urza_id,
                task_id=task_id,
            )
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    # Проверяем право создания программы.
    if current_user.role not in {
        UserRole.MANAGER,
        UserRole.ENGINEER,
        UserRole.ADMIN,
        UserRole.SUPERADMIN,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Создавать программы с текущей ролью запрещено.",
        )

    uploaded_file_keys: list[str] = []

    async def cleanup_uploaded_files() -> None:
        """Удаляет файлы, загруженные в рамках неудачного создания."""
        for key in uploaded_file_keys:
            try:
                await file_service.storage.delete(key=key)
            except Exception:
                logger.exception(
                    "Не удалось очистить новый файл после ошибки "
                    "создания программы: key=%s",
                    key,
                )

    try:
        # Загружаем обязательный скан.
        scan_content = await scan_file.read()

        if not scan_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Загруженный скан пуст.",
            )

        saved_scan = await file_service.upload(
            actor_id=current_user.id,
            content=scan_content,
            original_name=scan_file.filename or "scan",
            display_name=scan_file.filename or "Скан программы",
            extension=(
                "." + scan_file.filename.rsplit(".", 1)[1]
                if scan_file.filename and "." in scan_file.filename
                else ""
            ),
            mime_type=(
                scan_file.content_type or "application/octet-stream"
            ),
        )
        uploaded_file_keys.append(saved_scan.s3_key)

        # Редактируемый файл необязателен.
        editable_file_id = None

        if editable_file and editable_file.filename:
            editable_content = await editable_file.read()

            if not editable_content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Загруженный редактируемый файл пуст.",
                )

            saved_editable = await file_service.upload(
                actor_id=current_user.id,
                content=editable_content,
                original_name=editable_file.filename,
                display_name=editable_file.filename,
                extension=(
                    "." + editable_file.filename.rsplit(".", 1)[1]
                    if "." in editable_file.filename
                    else ""
                ),
                mime_type=(
                    editable_file.content_type
                    or "application/octet-stream"
                ),
            )
            uploaded_file_keys.append(saved_editable.s3_key)
            editable_file_id = saved_editable.id

        # Создаём запись программы.
        await program_service.create(
            user_id=current_user.id,
            urza_id=urza_id,
            program_type=program_type,
            program_number=normalized_program_number,
            scan_file_id=saved_scan.id,
            editable_file_id=editable_file_id,
            task_id=task_id,
        )

    except PermissionError as exc:
        await cleanup_uploaded_files()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        await cleanup_uploaded_files()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception:
        await cleanup_uploaded_files()
        raise

    # Возвращаем результат для обычного запроса или HTMX.
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url=f"/objects/urza/{urza_id}/programs",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
        task_service=task_service,
        tree_service=tree_service,
    )



@router.post("/urza/{urza_id}/programs/{program_id}/edit")
async def update_urza_program(
    request: Request,
    urza_id: UUID,
    program_id: UUID,
    program_type: Annotated[ProgramType, Form()],
    program_number: Annotated[str, Form()],
    current_user: Annotated[User, Depends(get_current_user)],
    object_service: Annotated[ObjectService, Depends(get_object_service)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    file_service: Annotated[
        FileService,
        Depends(get_file_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],
    scan_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
    editable_file: Annotated[
        UploadFile | None,
        FastAPIFile(),
    ] = None,
    remove_editable_file: Annotated[
        bool,
        Form(),
    ] = False,
):
    try:
        await object_service.get_object(
            user_id=current_user.id,
            object_type="urza",
            object_id=urza_id,
        )
    except ObjectAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к объекту запрещён.",
        ) from exc
    except ObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объект не найден.",
        ) from exc

    try:
        program = await program_service.get_by_id(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if program is None or program.urza_id != urza_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Программа не найдена.",
        )

    if program.status is not DocumentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Редактировать можно только черновик.",
        )

    if current_user.role not in {
        UserRole.ENGINEER,
        UserRole.ADMIN,
        UserRole.SUPERADMIN,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Редактировать программу с текущей ролью запрещено.",
        )

    has_editable_upload = bool(
        editable_file and editable_file.filename
    )

    if remove_editable_file and has_editable_upload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Нельзя одновременно удалить и загрузить "
                "редактируемый файл."
            ),
        )

    normalized_program_number = program_number.strip()

    if not normalized_program_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Номер программы не может быть пустым.",
        )

    if len(normalized_program_number) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Номер программы не должен превышать 255 символов.",
        )

    scan_file_id = None
    editable_file_id = None
    uploaded_file_keys: list[str] = []

    try:
        if scan_file and scan_file.filename:
            scan_content = await scan_file.read()

            if not scan_content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Загруженный скан пуст.",
                )

            saved_scan = await file_service.upload(
                actor_id=current_user.id,
                content=scan_content,
                original_name=scan_file.filename,
                display_name=scan_file.filename,
                extension=(
                    "." + scan_file.filename.rsplit(".", 1)[1]
                    if "." in scan_file.filename
                    else ""
                ),
                mime_type=(
                        scan_file.content_type
                        or "application/octet-stream"
                ),
            )
            scan_file_id = saved_scan.id
            uploaded_file_keys.append(saved_scan.s3_key)

        if has_editable_upload:
            editable_content = await editable_file.read()

            if not editable_content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Загруженный редактируемый файл пуст.",
                )

            saved_editable = await file_service.upload(
                actor_id=current_user.id,
                content=editable_content,
                original_name=editable_file.filename,
                display_name=editable_file.filename,
                extension=(
                    "." + editable_file.filename.rsplit(".", 1)[1]
                    if "." in editable_file.filename
                    else ""
                ),
                mime_type=(
                        editable_file.content_type
                        or "application/octet-stream"
                ),
            )
            editable_file_id = saved_editable.id
            uploaded_file_keys.append(saved_editable.s3_key)

        await program_service.update(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
            program_type=program_type,
            program_number=normalized_program_number,
            scan_file_id=scan_file_id,
            editable_file_id=editable_file_id,
            remove_editable_file=remove_editable_file,
        )

    except PermissionError as exc:
        for key in uploaded_file_keys:
            try:
                await file_service.storage.delete(key=key)
            except Exception:
                logger.exception(
                    "Не удалось очистить новый файл после ошибки "
                    "редактирования программы: key=%s",
                    key,
                )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        for key in uploaded_file_keys:
            try:
                await file_service.storage.delete(key=key)
            except Exception:
                logger.exception(
                    "Не удалось очистить новый файл после ошибки "
                    "редактирования программы: key=%s",
                    key,
                )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception:
        for key in uploaded_file_keys:
            try:
                await file_service.storage.delete(key=key)
            except Exception:
                logger.exception(
                    "Не удалось очистить новый файл после ошибки "
                    "редактирования программы: key=%s",
                    key,
                )
        raise

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url=f"/objects/urza/{urza_id}/programs",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
        task_service=task_service,
        tree_service=tree_service,
    )



@router.post("/urza/{urza_id}/programs/{program_id}/submit")
async def submit_urza_program(
    request: Request,
    urza_id: UUID,
    program_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],


):
    try:
        await program_service.submit_for_review(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
        task_service=task_service,
        tree_service=tree_service,
    )


@router.post("/urza/{urza_id}/programs/{program_id}/approve")
async def approve_urza_program(
    request: Request,
    urza_id: UUID,
    program_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],

):
    try:
        await program_service.approve(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
        task_service=task_service,
        tree_service=tree_service,
    )


@router.post("/urza/{urza_id}/programs/{program_id}/return")
async def return_urza_program(
    request: Request,
    urza_id: UUID,
    program_id: UUID,

    current_user: Annotated[User, Depends(get_current_user)],
    program_service: Annotated[
        ProgramService,
        Depends(get_program_service),
    ],
    task_service: Annotated[
        TaskService,
        Depends(get_task_service),
    ],
    tree_service: Annotated[
        TreeService,
        Depends(get_tree_service),
    ],
    comment: Annotated[str | None, Form()] = None,
):
    try:
        await program_service.return_to_draft(
            user_id=current_user.id,
            program_id=program_id,
            urza_id=urza_id,
            comment=comment,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return await _render_urza_programs(
        request=request,
        urza_id=urza_id,
        current_user=current_user,
        program_service=program_service,
        task_service=task_service,
        tree_service=tree_service,
    )
