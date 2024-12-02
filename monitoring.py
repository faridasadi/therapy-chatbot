import time
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PipelineMonitor:
    def __init__(self):
        self.total_messages = 0
        self.failed_messages = 0
        self.pipeline_stages = {}
        self.api_call_times: List[float] = []
        self.last_active_timestamp: float = time.time()
        self.last_heartbeat: float = time.time()
        self.unresponsive_periods = 0
        self.stage_failures = {}
        self.recovery_attempts = 0

    def _calculate_avg_processing_time(self) -> float:
        """Calculate average processing time across all stages"""
        total_time = 0
        total_counts = 0
        for stage_times in self.pipeline_stages.values():
            if stage_times:
                total_time += sum(stage_times)
                total_counts += len(stage_times)
        return round(total_time / max(total_counts, 1), 3)

    def record_pipeline_stage(self, stage_name: str, duration: float):
        """Record timing for a specific pipeline stage with error tracking"""
        if stage_name not in self.pipeline_stages:
            self.pipeline_stages[stage_name] = []
        self.pipeline_stages[stage_name].append(duration)
        self.last_active_timestamp = time.time()
        self.heartbeat()

    def record_message(self, success: bool = True):
        """Record message processing attempt"""
        self.total_messages += 1
        if not success:
            self.failed_messages += 1
        self.heartbeat()

    def record_api_call(self, duration: float):
        """Record API call duration"""
        self.api_call_times.append(duration)
        self.heartbeat()

    def record_stage_failure(self, stage_name: str):
        """Record a failure in a specific pipeline stage"""
        self.stage_failures[stage_name] = self.stage_failures.get(stage_name, 0) + 1
        self.failed_messages += 1

    def heartbeat(self):
        """Update heartbeat timestamp"""
        self.last_heartbeat = time.time()

    def check_responsiveness(self) -> Dict[str, Any]:
        """Check system responsiveness and return status with enhanced monitoring"""
        current_time = time.time()
        heartbeat_age = current_time - self.last_heartbeat
        active_age = current_time - self.last_active_timestamp
        
        # Define thresholds
        warning_threshold = 180  # 3 minutes
        critical_threshold = 300  # 5 minutes
        
        status = {
            "status": "healthy",
            "heartbeat_age": round(heartbeat_age, 2),
            "active_age": round(active_age, 2),
            "unresponsive_periods": self.unresponsive_periods,
            "recovery_attempts": self.recovery_attempts,
            "last_heartbeat": datetime.fromtimestamp(self.last_heartbeat).isoformat(),
            "last_active": datetime.fromtimestamp(self.last_active_timestamp).isoformat()
        }
        
        # Progressive status checks
        if heartbeat_age > critical_threshold:
            status["status"] = "critical"
            self.unresponsive_periods += 1
            logger.error(f"System critically unresponsive for {heartbeat_age:.1f} seconds")
            self._attempt_recovery()
        elif heartbeat_age > warning_threshold:
            status["status"] = "warning"
            logger.warning(f"System showing delayed response: {heartbeat_age:.1f} seconds")
            
        # Add performance indicators
        status["performance_indicators"] = {
            "message_rate": round(self.total_messages / max((current_time - self.last_active_timestamp), 1), 2),
            "error_rate": round(self.failed_messages / max(self.total_messages, 1), 3),
            "avg_processing_time": self._calculate_avg_processing_time()
        }
            
        return status

    def _attempt_recovery(self):
        """Attempt to recover from unresponsive state"""
        self.recovery_attempts += 1
        logger.warning(f"Attempting system recovery (attempt {self.recovery_attempts})")
        
        # Reset critical counters and timestamps
        self.last_heartbeat = time.time()
        self.last_active_timestamp = time.time()
        
        # Clear any stuck metrics
        if len(self.api_call_times) > 1000:
            self.api_call_times = self.api_call_times[-1000:]
        
        for stage in self.pipeline_stages:
            if len(self.pipeline_stages[stage]) > 1000:
                self.pipeline_stages[stage] = self.pipeline_stages[stage][-1000:]

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics with enhanced statistics"""
        current_time = time.time()
        responsiveness = self.check_responsiveness()
        
        # Calculate API performance metrics
        api_calls = len(self.api_call_times)
        avg_response_time = (
            round(sum(self.api_call_times) / api_calls, 3)
            if api_calls > 0 else 0
        )

        metrics = {
            "total_messages": self.total_messages,
            "failed_messages": self.failed_messages,
            "pipeline_stages": {},
            "api_performance": {
                "avg_response_time": avg_response_time,
                "total_calls": api_calls
            },
            "system_health": {
                "last_active": round(current_time - self.last_active_timestamp, 2),
                "status": responsiveness["status"],
                "unresponsive_periods": responsiveness["unresponsive_periods"],
                "recovery_attempts": responsiveness["recovery_attempts"]
            },
            "timestamp": datetime.now().isoformat()
        }

        # Calculate pipeline stage metrics
        for stage, timings in self.pipeline_stages.items():
            if timings:
                avg_time = sum(timings) / len(timings)
                max_time = max(timings)
                min_time = min(timings)
                metrics["pipeline_stages"][stage] = {
                    "avg": round(avg_time, 3),
                    "max": round(max_time, 3),
                    "min": round(min_time, 3),
                    "count": len(timings),
                    "failures": self.stage_failures.get(stage, 0)
                }

        return metrics

# Global monitor instance
pipeline_monitor = PipelineMonitor()

def monitor_pipeline_stage(stage_name: str):
    """Decorator to monitor pipeline stages with enhanced error handling"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                pipeline_monitor.record_pipeline_stage(stage_name, duration)
                return result
            except Exception as e:
                pipeline_monitor.record_stage_failure(stage_name)
                logger.error(f"Stage {stage_name} failed: {str(e)}")
                raise e

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                pipeline_monitor.record_pipeline_stage(stage_name, duration)
                return result
            except Exception as e:
                pipeline_monitor.record_stage_failure(stage_name)
                logger.error(f"Stage {stage_name} failed: {str(e)}")
                raise e

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

async def log_metrics_periodically(interval: int = 60):
    """Periodically log metrics with enhanced formatting"""
    logger.info("Starting metrics logging service...")
    while True:
        try:
            metrics = pipeline_monitor.get_metrics()
            log_message = "\n" + "="*50 + "\n"
            log_message += "MESSAGE FLOW MONITORING REPORT\n"
            log_message += "="*50 + "\n\n"
            
            # System health with enhanced visibility
            log_message += "🔋 SYSTEM HEALTH:\n"
            health_status = metrics['system_health']['status'].upper()
            status_icon = "✅" if health_status == "HEALTHY" else "⚠️"
            log_message += f"{status_icon} Status: {health_status}\n"
            log_message += f"├── Last Active: {metrics['system_health']['last_active']}s ago\n"
            log_message += f"├── Unresponsive Periods: {metrics['system_health']['unresponsive_periods']}\n"
            log_message += f"└── Recovery Attempts: {metrics['system_health']['recovery_attempts']}\n\n"
            
            # Message statistics
            log_message += "📊 Message Statistics:\n"
            log_message += f"├── Total Messages: {metrics['total_messages']}\n"
            log_message += f"├── Failed Messages: {metrics['failed_messages']}\n"
            success_rate = ((metrics['total_messages'] - metrics['failed_messages']) / max(metrics['total_messages'], 1)) * 100
            log_message += f"└── Success Rate: {success_rate:.1f}%\n\n"
            
            # API Performance
            log_message += "🌐 API Performance:\n"
            log_message += f"├── Average Response Time: {metrics['api_performance']['avg_response_time']:.3f}s\n"
            log_message += f"└── Total API Calls: {metrics['api_performance']['total_calls']}\n\n"
            
            # Pipeline stages performance
            log_message += "⚡ Pipeline Stages Performance:\n"
            for stage, stats in metrics['pipeline_stages'].items():
                log_message += f"├── {stage}:\n"
                log_message += f"│   ├── Average Time: {stats['avg']:.3f}s\n"
                log_message += f"│   ├── Max Time: {stats['max']:.3f}s\n"
                log_message += f"│   ├── Min Time: {stats['min']:.3f}s\n"
                log_message += f"│   ├── Processed: {stats['count']} messages\n"
                log_message += f"│   └── Failures: {stats['failures']}\n"
            
            logger.info(log_message)
            await asyncio.sleep(interval)
        except Exception as e:
            logger.error(f"Error logging metrics: {str(e)}")
            await asyncio.sleep(interval)
