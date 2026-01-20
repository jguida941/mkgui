"""Sample database module for testing the analyzer."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Status(Enum):
    """Task status enum."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Priority(Enum):
    """Task priority enum."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Task:
    """A task in the system."""
    title: str
    description: str
    status: Status = Status.TODO
    priority: Priority = Priority.MEDIUM


def create_task(
    title: str,
    description: str = "",
    priority: Priority = Priority.MEDIUM,
    project_id: Optional[int] = None,
) -> int:
    """Create a new task in the database.

    Args:
        title: The task title
        description: Optional task description
        priority: Task priority level
        project_id: Optional project to assign task to

    Returns:
        The ID of the created task
    """
    print(f"Creating task: {title}")
    return 1


def get_all_tasks(
    status: Optional[Status] = None,
    limit: int = 100,
) -> list[dict]:
    """Get all tasks from the database.

    Args:
        status: Filter by status (optional)
        limit: Maximum number of tasks to return

    Returns:
        List of task dictionaries
    """
    return [{"id": 1, "title": "Sample Task", "status": "todo"}]


def update_task_status(task_id: int, status: Status) -> None:
    """Update the status of a task.

    Args:
        task_id: The task ID to update
        status: The new status
    """
    print(f"Updating task {task_id} to {status}")


def delete_task(task_id: int) -> bool:
    """Delete a task from the database.

    Args:
        task_id: The task ID to delete

    Returns:
        True if deleted successfully
    """
    print(f"Deleting task {task_id}")
    return True


def export_tasks(output_path: Path, format: str = "json") -> None:
    """Export all tasks to a file.

    Args:
        output_path: Path to write the export file
        format: Export format (json, csv)
    """
    print(f"Exporting to {output_path} as {format}")


class TaskService:
    """Service class with static and class methods."""

    @staticmethod
    def count_tasks() -> int:
        """Count total tasks in the database."""
        return 42

    @classmethod
    def get_instance(cls) -> "TaskService":
        """Get a singleton instance of the service."""
        return cls()

    def regular_method(self) -> None:
        """This should NOT be detected in v1."""
        pass


def _private_helper() -> None:
    """This should NOT be detected (private)."""
    pass
