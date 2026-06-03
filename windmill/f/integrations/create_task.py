"""Windmill script: create_task — Google Tasks via resource."""


def main(title: str, due_date: str = "", notes: str = ""):
    return {
        "status": "accepted",
        "action": "create_task",
        "title": title,
        "due_date": due_date,
        "notes": notes,
    }
