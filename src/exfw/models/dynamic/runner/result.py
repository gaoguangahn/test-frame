"""增量保存 runner 任务状态，使中断后仍能找到已生成的数据。"""
import time
from exfw.pytest_framework.result.store import atomic_write_json


class TaskResultStore:
    def __init__(self, config, tasks, started_at):
        self.path = config.output_dir / "task_result.json"
        self.data = {
            "config_path": str(config.config_path), "test_path": str(config.test_path),
            "output_dir": ".", "rounds": config.rounds,
            "started_at": started_at, "stopped_at": None, "duration_seconds": None,
            "status": "running", "summary": {},
            "tasks": [{"testbed": task.testbed_name, "main_serial": task.main_serial,
                       "output_dir": task.output_dir.relative_to(config.output_dir).as_posix(),
                       "session_result": (task.output_dir / "session_result.json").relative_to(config.output_dir).as_posix(),
                       "status": "pending", "exit_code": None, "duration_seconds": None,
                       "processing": None} for task in tasks],
        }
        self.save()

    def save(self):
        tasks = self.data["tasks"]
        self.data["summary"] = {"total": len(tasks),
            "passed": sum(item["status"] == "passed" for item in tasks),
            "failed": sum(item["status"] == "failed" for item in tasks),
            "interrupted": sum(item["status"] == "interrupted" for item in tasks),
            "pending": sum(item["status"] in ("pending", "running") for item in tasks)}
        atomic_write_json(self.path, self.data)

    def update(self, serial, **values):
        item = next(item for item in self.data["tasks"] if item["main_serial"] == serial)
        item.update(values)
        self.save()

    def finish(self, status):
        now = time.time()
        for item in self.data["tasks"]:
            if item["status"] in ("pending", "running"):
                item["status"] = "interrupted"
        self.data.update(status=status, stopped_at=now,
                         duration_seconds=round(now - self.data["started_at"], 3))
        self.save()
