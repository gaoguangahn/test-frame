class LogMemoryIoSheet:
    """专门处理报表生成的类"""

    MEMORY_METRICS = {
        "/proc/meminfo": [
            "MemTotal",
            "MemFree",
            "MemAvailable",
            "Active(anon)",
            "Inactive(anon)",
            "Active(file)",
            "Inactive(file)",
            "Unevictable",
            "Mlocked",
            "SwapTotal",
            "SwapFree",
            "Slab",
            "SUnreclaim",
            "DMA-BufUsed",
            "DMA-BufCache",
        ],
        "/proc/vmstat": [
            "direct_reclaim",
            "compact_stall",
            "compact_success",
            "workingset_refault_anon",
            "workingset_refault_file",
            "pgpgin",
            "pgpgout",
            "pswpin",
            "pswpout",
            "kswapd_high_wmark_hit_quickly",
            "kswapd_low_wmark_hit_quickly",
        ],
        "/proc/pressure/memory": [
            "some_avg10",
            "some_avg60",
            "some_avg300",
            "full_avg10",
            "full_avg60",
            "full_avg300",
        ],
        "/dev/memcg/memory.psi_health_info": [
            "ProtectLru",
            "hyperhold_out_times",
            "hyperhold_out_comp_size",
            "hyperhold_out_ori_size",
            "hyperhold_in_times",
            "hyperhold_in_comp_size",
            "hyperhold_in_ori_size",
            "zswapd_wake_up",
            "zswapd_empty_round",
            "zswapd_swapout",
        ],
        "dumpsys_memory": [
            "FreeRAM",
            "DMA-BUF_mapped",
            "DMA-BUF_unmapped",
            "GPU_dmabuf",
            "GPU_private",
            "UsedRAM_usedpss",
            "UsedRAM_kernel",
            "ZRAM_physical_used",
            "ZRAM_swap",
            "ZRAM_total_swap",
        ],
    }

    def __init__(self, excel_handler):
        self.excel = excel_handler

    def generate_all(self, sheets_data):
        """生成全部 Memory / IO 相关报表。"""

        self.create_memory_data_sheet(sheets_data.get("proc_data", []))
        self.create_memory_log_sheet(sheets_data.get("memory_log_data", []))
        self.create_io_measure_sheet(sheets_data.get("measure_data", []))

    def create_memory_data_sheet(self, proc_data):
        """
        内存数据表格
        处理/proc/meminfo、/proc/vmstat、/proc/pressure/memory、memory.psi_health_info数据，汇总统计主要内存指标
        :return: summary_data，便于后续绘制趋势或做统计分析
        """

        titles = {
            "10.内存数据": [
                "sn",
                "loop",
                "case",
                {"/proc/meminfo": self.MEMORY_METRICS["/proc/meminfo"]},
                {"/proc/vmstat": self.MEMORY_METRICS["/proc/vmstat"]},
                {"/proc/pressure/memory": self.MEMORY_METRICS["/proc/pressure/memory"]},
                {
                    "/dev/memcg/memory.psi_health_info": self.MEMORY_METRICS[
                        "/dev/memcg/memory.psi_health_info"
                    ]
                },
            ]
        }
        self.excel.add_sheet(titles, proc_data)
        print("10.内存数据页 已生成")
        return

    def create_memory_log_sheet(self, merged_data):
        """内存日志数据表格"""

        titles = {
            "11.内存日志": [
                "sn",
                "loop",
                {"dumpsys meminfo": self.MEMORY_METRICS["dumpsys_memory"]},
                {"/data/log/jank/health/mem_procs_killed.log": ["am_kill"]},
                {"logcat日志": ["lmkd"]},
            ]
        }

        self.excel.add_sheet(titles, merged_data)
        print("11.内存日志页 已生成")

    def create_io_measure_sheet(self, measure_data):
        """IOMeasure数据表格"""

        titles = {
            "12.IOMeasure": [
                "sn",
                "loop",
                "log_name",
                {
                    "Latency-fs": [
                        "read_cnt",
                        "write_cnt",
                        "other_cnt",
                        "all_cnt",
                        "read(4~8ms)",
                        "write(4~8ms)",
                        "read(8~16ms)",
                        "write(8~16ms)",
                        "read(>16ms)",
                        "write(>16ms)",
                    ]
                },
                {
                    "Latency-blk": [
                        "read_cnt",
                        "write_cnt",
                        "other_cnt",
                        "all_cnt",
                        "read(4~8ms)",
                        "write(4~8ms)",
                        "read(8~16ms)",
                        "write(8~16ms)",
                        "read(>16ms)",
                        "write(>16ms)",
                    ]
                },
                {
                    "Latency-scsi": [
                        "read_cnt",
                        "write_cnt",
                        "other_cnt",
                        "all_cnt",
                        "read(4~8ms)",
                        "write(4~8ms)",
                        "read(8~16ms)",
                        "write(8~16ms)",
                        "read(>16ms)",
                        "write(>16ms)",
                    ]
                },
            ]
        }
        self.excel.add_sheet(titles, measure_data)
        print("12.IOMeasure页 已生成")
        return
