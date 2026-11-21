from django.db import models


class SavedLesson(models.Model):
    teacher_code = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=120)
    lesson_date = models.DateField(auto_now_add=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    results_json = models.JSONField(default=list)

    class Meta:
        ordering = ['-created_at']
