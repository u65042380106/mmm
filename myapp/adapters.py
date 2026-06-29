# myapp/adapters.py
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    
    # ทำงานเมื่อ "สมัครสมาชิกใหม่" ผ่าน Google ครั้งแรก
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        
        # ตรวจสอบว่าอีเมลของผู้ใช้รายนี้ อยู่ในรายชื่อ ADMIN_EMAILS หรือไม่
        if user.email in getattr(settings, 'ADMIN_EMAILS', []):
            user.is_staff = True        # ให้สิทธิ์เข้าหน้าแอดมินหลังบ้าน
            user.is_superuser = True    # ให้สิทธิ์แอดมินสูงสุดทำได้ทุกอย่าง
            user.save()
        return user
            
    # ทำงานเมื่อ "ล็อกอินซ้ำ" ในครั้งต่อๆ ไป (เผื่อกรณีเราเพิ่งแอดอีเมลเขาเป็นแอดมินทีหลัง)
    def pre_social_login(self, request, sociallogin):
        user = sociallogin.user
        if user.id and user.email in getattr(settings, 'ADMIN_EMAILS', []):
            if not user.is_staff or not user.is_superuser:
                user.is_staff = True
                user.is_superuser = True
                user.save()