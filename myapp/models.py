# myapp/models.py
from django.db import models
from django.contrib.auth.models import User

class SearchHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="ผู้ใช้งาน")
    keyword = models.CharField(max_length=255, verbose_name="คำค้นหา")
    ai_result = models.TextField(blank=True, null=True, verbose_name="ผลวิเคราะห์จาก AI")
    
    # เพิ่มฟิลด์เก็บรายการสินค้าในรูปแบบข้อความ JSON
    products_json = models.TextField(blank=True, default="[]", verbose_name="สินค้าดิบจาก Lazada")
    
    # เพิ่มสถานะการทำงาน: pending (กำลังรอ), success (เสร็จแล้ว), error (ระบบล่ม)
    status = models.CharField(max_length=20, default='pending', verbose_name="สถานะ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันเวลาที่ค้นหา")

    class Meta:
        ordering = ['-created_at']

class ComparisonRecord(models.Model):
    history = models.ForeignKey(SearchHistory, on_delete=models.CASCADE, related_name='comparisons')
    selected_items_json = models.TextField(verbose_name="ข้อมูลสินค้าที่เลือกเปรียบเทียบ (JSON)")
    ai_recommendation = models.TextField(blank=True, null=True, verbose_name="คำแนะนำจาก AI")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at'] # ให้เรียงจากล่าสุดไปเก่าสุด