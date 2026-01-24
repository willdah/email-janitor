from simplegmail import Gmail
from simplegmail.message import Message


gmail: Gmail | None = None


def get_gmail_client():
    """
    Returns a Gmail client instance. If the client is not initialized, it will be initialized using the client_secret.json file.
    """
    global gmail
    if gmail is None:
        gmail = Gmail()
    return gmail


def get_unread_emails() -> list[Message]:
    """
    Uses the Gmail client to get a list of unread emails.
    """
    gmail: Gmail = get_gmail_client()
    unread_emails: list[Message] = gmail.get_unread_messages()
    return unread_emails
