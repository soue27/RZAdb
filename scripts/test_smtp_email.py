import asyncio

from app.core.config import get_settings
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender


async def main() -> None:
    settings = get_settings()
    sender = SMTPEmailSender(settings)

    recipient = input("Тестовый адрес получателя: ").strip()

    if not recipient or "@" not in recipient:
        raise ValueError("Укажи корректный email")

    print(f"\nПолучатель: {recipient}")
    print("Тема: Тест SMTP — RZAdb")
    print("Содержимое: Проверка отправки email-сводок RZAdb.")

    confirmation = input(
        '\nДля отправки введи SEND TEST EMAIL: '
    ).strip()

    if confirmation != "SEND TEST EMAIL":
        print("Отправка отменена.")
        return

    await sender.send(
        to=recipient,
        subject="Тест SMTP — RZAdb",
        body="Проверка отправки email-сводок RZAdb.",
        html_body="""
        <html>
            <body>
                <h2>RZAdb</h2>
                <p>Проверка отправки email-сводок.</p>
                <p>SMTP-подключение и отправка работают.</p>
            </body>
        </html>
        """,
    )

    print("Письмо передано SMTP-серверу.")


if __name__ == "__main__":
    asyncio.run(main())