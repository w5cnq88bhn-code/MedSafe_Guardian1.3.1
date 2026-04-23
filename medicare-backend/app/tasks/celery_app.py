from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "medicare",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.miss_detect_task",
        "app.tasks.reminder_task",
        "app.tasks.lstm_task",
        "app.tasks.apriori_task",
    ],
)

celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True   # 统一使用 UTC，与数据库存储保持一致

celery_app.conf.beat_schedule = {
    # 每30分钟检测漏服
    "check-missed-every-30min": {
        "task":     "app.tasks.miss_detect_task.check_missed_medications",
        "schedule": crontab(minute="*/30"),
    },
    # 每5分钟检查即将到来的服药时间
    "send-reminders-every-5min": {
        "task":     "app.tasks.reminder_task.send_scheduled_reminders",
        "schedule": crontab(minute="*/5"),
    },
    # 每日凌晨2点运行LSTM预测
    "lstm-predictions-daily": {
        "task":     "app.tasks.lstm_task.run_lstm_predictions",
        "schedule": crontab(hour=2, minute=0),
    },
    # 每周日凌晨3点运行Apriori挖掘
    "apriori-mining-weekly": {
        "task":     "app.tasks.apriori_task.run_apriori_mining",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
    },
}
