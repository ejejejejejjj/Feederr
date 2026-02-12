"""
Session Scheduler
Auto-renews indexer sessions daily at random times between 8-9 AM
"""
import asyncio
import logging
from datetime import datetime, time, timedelta
import random
from typing import Dict

logger = logging.getLogger(__name__)


class SessionScheduler:
    """Manages automatic session renewal for indexers"""
    
    def __init__(self, auth_manager, indexer_config):
        self.auth_manager = auth_manager
        self.indexer_config = indexer_config
        self.scheduled_times: Dict[str, time] = {}
        self.running = False
        self._task = None
    
    def _generate_random_time(self) -> time:
        """Generate random time between 8:00 and 9:00 AM"""
        hour = 8
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        return time(hour, minute, second)
    
    def _schedule_indexers(self):
        """Assign random renewal times to all indexers"""
        indexers = self.indexer_config.get_all_indexers()
        
        for indexer_id in indexers.keys():
            if indexer_id not in self.scheduled_times:
                renewal_time = self._generate_random_time()
                self.scheduled_times[indexer_id] = renewal_time
                logger.info(f"Scheduled {indexer_id} session renewal at {renewal_time.strftime('%H:%M:%S')}")
    
    async def _check_and_renew(self):
        """Check if any indexer needs renewal and execute it"""
        now = datetime.now().time()
        current_minute = now.replace(second=0, microsecond=0)
        
        for indexer_id, scheduled_time in self.scheduled_times.items():
            scheduled_minute = scheduled_time.replace(second=0, microsecond=0)
            
            # Check if it's time to renew (within the same minute)
            if current_minute == scheduled_minute:
                # Check if indexer still exists and is enabled
                indexer_cfg = self.indexer_config.get_indexer(indexer_id)
                if not indexer_cfg:
                    logger.warning(f"Indexer {indexer_id} no longer exists, removing from schedule")
                    continue
                
                if not indexer_cfg.get("enabled", False):
                    logger.info(f"Skipping renewal for disabled indexer: {indexer_id}")
                    continue
                
                logger.info(f"Auto-renewing session for {indexer_id}")
                try:
                    success = await self.auth_manager.refresh_session(indexer_id)
                    if success:
                        logger.info(f"Successfully renewed session for {indexer_id}")
                    else:
                        logger.error(f"Failed to renew session for {indexer_id}")
                except Exception as e:
                    logger.error(f"Error renewing session for {indexer_id}: {e}")
    
    async def _scheduler_loop(self):
        """Main scheduler loop that runs continuously"""
        logger.info("Session scheduler started")
        
        while self.running:
            try:
                # Re-schedule indexers (in case new ones were added)
                self._schedule_indexers()
                
                # Check and renew
                await self._check_and_renew()
                
                # Sleep for 30 seconds before next check
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)
    
    def start(self):
        """Start the scheduler"""
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._scheduler_loop())
            logger.info("Session scheduler task created")
    
    async def stop(self):
        """Stop the scheduler"""
        if self.running:
            self.running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("Session scheduler stopped")


# Global instance
session_scheduler = None


def get_session_scheduler(auth_manager=None, indexer_config=None):
    """Get or create global session scheduler"""
    global session_scheduler
    
    if session_scheduler is None and auth_manager and indexer_config:
        session_scheduler = SessionScheduler(auth_manager, indexer_config)
    
    return session_scheduler
