from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="RZAdb",
    )

    return app


app = create_app()