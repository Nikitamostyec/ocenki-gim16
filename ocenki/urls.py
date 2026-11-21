from django.urls import path
from tracker import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_teacher, name='login_teacher'),
    path('logout/', views.logout_teacher, name='logout_teacher'),
    path('import/', views.import_file, name='import_file'),
    path('select-col/', views.select_column, name='select_column'),
    path('confirm-import/', views.confirm_import, name='confirm_import'),
    path('cancel-import/', views.cancel_import, name='cancel_import'),
    path('click/<int:student_id>/', views.add_point, name='add_point'),
    path('undo/', views.undo, name='undo'),
    path('reset/', views.reset, name='reset'),
    path('clear/', views.clear_class, name='clear_class'),
    path('ee/', views.update_ee, name='update_ee'),
    path('finish-lesson/', views.finish_lesson, name='finish_lesson'),
    path('export/', views.export_excel, name='export_excel'),
    path('export-saved/<int:lesson_id>/', views.export_saved_lesson, name='export_saved_lesson'),
    path('export-day/', views.export_day_excel, name='export_day_excel'),
    path('delete-saved/<int:lesson_id>/', views.delete_saved_lesson, name='delete_saved_lesson'),
]
