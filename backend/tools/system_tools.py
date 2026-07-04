"""
System Monitoring Tools.
Real-time CPU, RAM, disk, network, and GPU telemetry plus process-tree
introspection and active network connections — the sensory layer that gives
the agent situational awareness of the host machine.
"""

import asyncio
import os
import shutil
import subprocess
import time
from typing import Dict

import psutil

from tools.base import Tool, ToolResult


class SystemMetricsTool(Tool):
    name = "system_metrics"
    description = (
        "Get real-time system resource metrics: CPU load (overall + per-core), "
        "memory/swap usage, per-disk usage, network I/O counters, GPU utilization "
        "(if an NVIDIA GPU is present), and system uptime."
    )
    parameters_schema = {}

    async def execute(self, args: Dict) -> ToolResult:
        try:
            cpu_percent, cpu_per_core = await asyncio.to_thread(self._sample_cpu)
            cpu_freq = psutil.cpu_freq()
            try:
                load_avg = os.getloadavg()
            except (AttributeError, OSError):
                load_avg = (0.0, 0.0, 0.0)

            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            disks = []
            for part in psutil.disk_partitions(all=False):
                if not part.mountpoint or "loop" in part.device:
                    continue
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except (PermissionError, OSError):
                    continue
                disks.append(
                    {
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    }
                )

            net_io = psutil.net_io_counters()
            network = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
            }

            gpu = await asyncio.to_thread(self._get_gpu_stats)

            return ToolResult(
                success=True,
                data={
                    "cpu": {
                        "percent": cpu_percent,
                        "per_core": cpu_per_core,
                        "cores": psutil.cpu_count(logical=True),
                        "physical_cores": psutil.cpu_count(logical=False),
                        "freq_mhz": round(cpu_freq.current, 0) if cpu_freq else None,
                        "load_avg": list(load_avg),
                    },
                    "memory": {
                        "total": mem.total,
                        "used": mem.used,
                        "available": mem.available,
                        "percent": mem.percent,
                    },
                    "swap": {
                        "total": swap.total,
                        "used": swap.used,
                        "percent": swap.percent,
                    },
                    "disks": disks,
                    "network": network,
                    "gpu": gpu,
                    "uptime_seconds": time.time() - psutil.boot_time(),
                    "timestamp": time.time(),
                },
                message="System metrics retrieved",
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to get system metrics: {e}")

    @staticmethod
    def _sample_cpu():
        # First call with interval primes measurement; safe to call repeatedly
        # since it's dispatched to a worker thread and won't block the loop.
        cpu_percent = psutil.cpu_percent(interval=0.2)
        cpu_per_core = psutil.cpu_percent(interval=0.0, percpu=True)
        return cpu_percent, cpu_per_core

    @staticmethod
    def _get_gpu_stats():
        if not shutil.which("nvidia-smi"):
            return None
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if out.returncode != 0:
                return None
            gpus = []
            for line in out.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpus.append(
                        {
                            "name": parts[0],
                            "utilization_percent": float(parts[1]),
                            "memory_used_mb": float(parts[2]),
                            "memory_total_mb": float(parts[3]),
                            "temperature_c": float(parts[4]),
                        }
                    )
            return gpus or None
        except Exception:
            return None


class ProcessTreeTool(Tool):
    name = "process_tree"
    description = "Get the running process list as a parent-child tree structure, for visualizing what's driving system load"
    parameters_schema = {
        "limit": "(optional) Max number of processes to include. Default 300.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        limit = int(args.get("limit", 300))
        try:
            procs = {}
            for p in psutil.process_iter(
                ["pid", "ppid", "name", "username", "cpu_percent", "memory_percent", "status"]
            ):
                try:
                    info = p.info
                    procs[info["pid"]] = {
                        "pid": info["pid"],
                        "ppid": info["ppid"],
                        "name": info["name"] or "?",
                        "user": info["username"],
                        "cpu": round(info["cpu_percent"] or 0, 1),
                        "memory": round(info["memory_percent"] or 0, 1),
                        "status": info["status"],
                        "children": [],
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                if len(procs) >= limit:
                    break

            roots = []
            for pid, node in procs.items():
                ppid = node["ppid"]
                if ppid in procs and ppid != pid:
                    procs[ppid]["children"].append(node)
                else:
                    roots.append(node)

            return ToolResult(
                success=True,
                data={"tree": roots, "count": len(procs)},
                message=f"{len(procs)} process(es) mapped",
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to build process tree: {e}")


class NetworkConnectionsTool(Tool):
    name = "network_connections"
    description = "List active network connections and listening ports on this machine"
    parameters_schema = {
        "kind": "(optional) 'inet', 'tcp', 'udp', or 'listening'. Default 'inet'.",
        "limit": "(optional) Max results. Default 100.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        kind = args.get("kind", "inet")
        limit = int(args.get("limit", 100))
        query_kind = "inet" if kind == "listening" else kind
        try:
            conns = []
            for c in psutil.net_connections(kind=query_kind):
                if kind == "listening" and c.status != psutil.CONN_LISTEN:
                    continue
                laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                conns.append(
                    {
                        "pid": c.pid,
                        "type": "TCP" if c.type == 1 else "UDP",
                        "local_address": laddr,
                        "remote_address": raddr,
                        "status": c.status,
                    }
                )
                if len(conns) >= limit:
                    break
            return ToolResult(
                success=True,
                data={"connections": conns, "count": len(conns)},
                message=f"{len(conns)} connection(s)",
            )
        except psutil.AccessDenied:
            return ToolResult(
                success=False,
                message="Permission denied — some connections require elevated privileges",
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to list connections: {e}")


ALL_SYSTEM_TOOLS = [
    SystemMetricsTool(),
    ProcessTreeTool(),
    NetworkConnectionsTool(),
]
