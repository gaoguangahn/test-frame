"""启动和点击报告共用的线程状态列序，与现有汇总页一致。"""

THREAD_STATE_COLUMNS = (
    "running_dur_ns",
    "runnable_dur_ns",
    "uninterruptible_sleep_dur_ns",
    "interruptible_sleep_dur_ns",
    "uninterruptible_io_sleep_dur_ns",
    "uninterruptible_non_io_sleep_dur_ns",
)
