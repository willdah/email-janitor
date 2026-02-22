from simplegmail import Gmail
from simplegmail.message import Message

gmail: Gmail | None = None


def get_gmail_client():
    """
    Returns a Gmail client instance. If the client is not initialized, it will be
    initialized using the client_secret.json file.
    """
    global gmail
    if gmail is None:
        gmail = Gmail()
    return gmail


def get_unread_emails() -> list[Message]:
    """
    Uses the Gmail client to get a list of unread emails from the inbox only.
    Filters out sent messages and already processed emails using Gmail's query syntax
    for efficient server-side filtering.
    """
    gmail: Gmail = get_gmail_client()
    # Use Gmail query syntax to filter: in inbox, not in sent folder, and not already processed
    unread_emails: list[Message] = gmail.get_unread_messages(query="in:inbox -in:sent -label:EmailJanitor-Processed")
    return unread_emails


def get_label_id_by_name(label_name: str) -> str:
    """
    Gets a Gmail label ID by name. Creates the label if it doesn't exist.

    Args:
        label_name: The name of the label to get or create

    Returns:
        The label ID as a string
    """
    gmail: Gmail = get_gmail_client()
    service = gmail.service

    # Get all labels
    labels = service.users().labels().list(userId="me").execute()

    # Check if label exists
    for label in labels.get("labels", []):
        if label["name"] == label_name:
            return label["id"]

    # Label doesn't exist, create it
    label_obj = {
        "name": label_name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    created_label = service.users().labels().create(userId="me", body=label_obj).execute()
    return created_label["id"]


def apply_label_to_message(message: Message, label_name: str, remove_inbox: bool = False) -> None:
    """
    Applies a label to a Gmail message by name. The label will be created if it doesn't exist.
    This operation does not mark the email as read.

    Args:
        message: The Message object to apply the label to
        label_name: The name of the label to apply
        remove_inbox: If True, removes the INBOX label (archives the email)
    """
    gmail: Gmail = get_gmail_client()
    service = gmail.service

    # Get the label ID
    label_id = get_label_id_by_name(label_name)

    # Prepare the modify body
    modify_body = {"addLabelIds": [label_id]}

    # If remove_inbox is True, also remove the INBOX label
    if remove_inbox:
        modify_body["removeLabelIds"] = ["INBOX"]

    # Apply the label using the Gmail API modify method
    # This only adds/removes labels and doesn't affect read status
    service.users().messages().modify(userId="me", id=message.id, body=modify_body).execute()
