import uuid

from patchpilot.models import AgentTask, Repository, TaskEvent


def test_repository_and_task_list_api(client, db):
    response = client.post(
        "/api/repositories",
        json={"full_name": "octo/demo", "test_command": "pytest -q"},
    )
    assert response.status_code == 201
    repository_id = response.json()["id"]
    response = client.get("/api/repositories")
    assert response.status_code == 200
    assert response.json()[0]["full_name"] == "octo/demo"

    task = AgentTask(
        repository_id=uuid.UUID(repository_id),
        github_issue_number=10,
        github_issue_url="https://github.com/octo/demo/issues/10",
        title="Demo",
        status="completed",
        current_stage="maintainers_notified",
    )
    db.add(task)
    db.commit()
    response = client.get("/api/tasks?status=completed&page=1&page_size=5")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_approval_endpoint_and_sse(client, db):
    repository = Repository(
        name="demo",
        owner="octo",
        full_name="octo/demo",
        github_url="https://github.com/octo/demo",
    )
    db.add(repository)
    db.flush()
    task = AgentTask(
        repository_id=repository.id,
        github_issue_number=11,
        github_issue_url="https://github.com/octo/demo/issues/11",
        title="Terminal event demo",
        status="completed",
        current_stage="maintainers_notified",
    )
    db.add(task)
    db.flush()
    db.add(
        TaskEvent(
            task_id=task.id,
            event_type="workflow.transition",
            stage="maintainers_notified",
            summary="Done",
            details={"simulated": True},
        )
    )
    db.commit()
    response = client.get(f"/api/tasks/{task.id}")
    assert response.status_code == 200
    with client.stream("GET", f"/api/tasks/{task.id}/stream") as stream:
        body = "\n".join(stream.iter_lines())
    assert "event: task-event" in body
    assert "event: end" in body

