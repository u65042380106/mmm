# myapp/views.py
import requests
import threading
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User 
from django.core.exceptions import PermissionDenied 
from django.contrib import messages
from myapp.models import SearchHistory
from django.http import HttpResponse 
import traceback
from django.db.models import Count

# 1. หน้าแรกของเว็บไซต์ (Index)
def index_view(request):
    popular_searches = (
        SearchHistory.objects.values('keyword')
        .annotate(search_count=Count('keyword'))
        .order_by('-search_count')[:10]
    )
    return render(request, 'index.html', {'popular_searches': popular_searches})

# 2. หน้าฟอร์มกรอกคำค้นหาพร้อม Filter 
@login_required
def search_view(request):
    return render(request, 'search.html')

# 3. หน้าตั้งค่าโปรไฟล์สมาชิก (ปรับปรุงรองรับการเปลี่ยน Username และชื่อ-นามสกุล)
@login_required
def profile_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        if username and username != request.user.username:
            if User.objects.filter(username=username).exists():
                messages.error(request, '❌ ชื่อผู้ใช้นี้มีคนใช้งานแล้ว กรุณาเลือกชื่ออื่นครับ')
                return redirect('profile')
            request.user.username = username
            
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save()
        
        messages.success(request, '✅ อัปเดตข้อมูลโปรไฟล์เรียบร้อยแล้ว!')
        return redirect('profile')
        
    return render(request, 'profile.html')

# 4. ฟังก์ชันแอบทำงานเบื้องหลัง (ส่งข้อมูลหา n8n และบันทึกฟิลเตอร์)
def run_n8n_in_background(history_id, payload):
    try:
        N8N_WEBHOOK_URL = 'http://localhost:5678/webhook-test/shopee-search'
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=None)
        
        if response.status_code == 200:
            result_data = response.json()
            history = SearchHistory.objects.get(id=history_id)
            history.ai_result = result_data.get('ai_analysis', 'ไม่มีผลวิเคราะห์')
            
            # 🌟 แพ็กข้อมูลตัวกรองดาว (min_rating) รวมเข้าไว้กับข้อมูลสินค้า
            combined_data = {
                'products': result_data.get('products', []),
                'filters': {
                    'min_price': payload.get('min_price', ''),
                    'max_price': payload.get('max_price', ''),
                    'ship_from': payload.get('ship_from', 'all'),
                    'min_rating': payload.get('min_rating', ''),  # บันทึกคะแนนดาวขั้นต่ำ
                    'ai_mode': payload.get('ai_mode', 'balanced')
                }
            }
            history.products_json = json.dumps(combined_data, ensure_ascii=False)
            history.status = 'success' 
            history.save()
    except Exception:
        try:
            history = SearchHistory.objects.get(id=history_id)
            history.status = 'error'
            history.ai_result = "เกิดข้อผิดพลาดในการเชื่อมต่อระบบวิเคราะห์ข้อมูล"
            history.save()
        except: 
            pass

# 5. หน้าประตูกลางรับคำค้นหาและฟิลเตอร์ดาว
@login_required
def dashboard_view(request):
    try:  
        keyword = request.GET.get('keyword', '').strip()
        min_price = request.GET.get('min_price', '').strip()
        max_price = request.GET.get('max_price', '').strip()
        ship_from = request.GET.get('ship_from', 'all')
        min_rating = request.GET.get('min_rating', '').strip()
        ai_mode = request.GET.get('ai_mode', 'balanced')
        
        if not keyword:
            return redirect('search')
            
        ai_filter_parts = []
        
        # 🌟 1. เพิ่มคำสั่งให้ AI วิเคราะห์ชื่อสินค้า (Title) และยี่ห้อจาก Keyword อย่างเข้มงวด
        ai_filter_parts.append(f"โปรดวิเคราะห์ชื่อสินค้า (Title) อย่างละเอียดเทียบกับคำค้นหา '{keyword}' หากในคำค้นหามีการระบุ 'ยี่ห้อ' หรือ 'รุ่น' ให้คัดเลือกเฉพาะสินค้าที่เป็นยี่ห้อ/รุ่นนั้นจริงๆ และให้ตัดสินค้าที่จงใจใส่ชื่อยี่ห้อมาหลอก (Spam Keyword) ทิ้งไปทันที")

        if min_price:
            ai_filter_parts.append(f"ต้องมีราคาตั้งแต่ {min_price} บาทขึ้นไป")
        if max_price:
            ai_filter_parts.append(f"ต้องมีราคาไม่เกิน {max_price} บาท")
            
        if ship_from == 'local':
            ai_filter_parts.append("ต้องส่งจากภายในประเทศหรือในไทยเท่านั้น ห้ามเอาต่างประเทศ")
        elif ship_from == 'overseas': 
            ai_filter_parts.append("ต้องส่งจากต่างประเทศเท่านั้น (แต่ถ้าสถานที่จัดส่งระบุเป็น 'ไม่ระบุ' ให้อนุโลมถือว่าเป็นต่างประเทศและนับรวมไปด้วยทันที)")

        if min_rating:
            ai_filter_parts.append(f"ต้องมีระดับคะแนนรีวิวเฉลี่ยไม่ต่ำกว่า {min_rating} ดาวขึ้นไป สินค้าชิ้นไหนได้คะแนนดาวน้อยกว่านี้ให้คัดออกทันที")

        if ai_mode == 'safe':
            ai_filter_parts.append("เน้นคัดเลือกเฉพาะสินค้าที่มีความน่าเชื่อถือสูงมาก มีรีวิวเยอะ และดาวสูง")
        elif ai_mode == 'budget':
            ai_filter_parts.append("เน้นคัดเลือกสินค้าที่ราคาประหยัดและคุ้มค่าที่สุด โดยยังคงมาตรฐานที่ดี")
        else:
            ai_filter_parts.append("ให้จัดเรียงสินค้าแบบสมดุลระหว่างราคาที่คุ้มค่าและความน่าเชื่อถือ")

        # รวมคำสั่งทั้งหมดเข้าด้วยกัน
        ai_filter_text = " และ ".join(ai_filter_parts)
            
        history = SearchHistory.objects.create(
            user=request.user,
            keyword=keyword,
            status='pending'
        )
        
        payload = {
            'keyword': keyword,
            'min_price': min_price,
            'max_price': max_price,
            'ship_from': ship_from,
            'min_rating': min_rating, 
            'ai_mode': ai_mode,
            'ai_filter': ai_filter_text  # 🚀 ส่งคำสั่งที่รวมเรื่องการเช็ก Title ไปให้ n8n
        }
        
        threading.Thread(target=run_n8n_in_background, args=(history.id, payload)).start()
        return redirect('history')

    except Exception as e:  
        error_html = f"""
        <div style="padding: 20px; font-family: monospace; background: #fff5f5; color: #c53030; border: 2px solid #feb2b2; border-radius: 8px; margin: 20px;">
            <h2 style="margin-top: 0; color: #9b2c2c;">🚨 เจอตัวการบั๊กระบบแดชบอร์ดแล้ว!</h2>
            <p><b>ข้อผิดพลาด:</b> {str(e)}</p>
            <hr style="border: 0; border-top: 1px solid #feb2b2; margin: 15px 0;">
            <p><b>รายละเอียดเชิงลึก (Traceback):</b></p>
            <pre style="background: #fff; padding: 15px; border-radius: 4px; border: 1px solid #fee2e2; overflow-x: auto;">{traceback.format_exc()}</pre>
        </div>
        """
        return HttpResponse(error_html)

# 6. หน้าแสดงรายการประวัติทั้งหมด
@login_required
def history_view(request):
    histories = SearchHistory.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'history.html', {'histories': histories})

# 7. หน้าแสดงรายละเอียดเจาะลึกหน้าแดชบอร์ด
@login_required
def result_detail_view(request, history_id):
    history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
    parsed_data = json.loads(history.products_json) if history.products_json else {}
    
    if isinstance(parsed_data, list):
        products = parsed_data
        filters = {}
    else:
        products = parsed_data.get('products', [])
        filters = parsed_data.get('filters', {})

    context = {
        'keyword': history.keyword,
        'ai_analysis': history.ai_result,
        'products': products,
        'created_at': history.created_at,
        
        # ส่งค่าตัวแปรกลับไปโชว์ในกล่องป้าย Badges บนหน้าเว็บ
        'min_price': filters.get('min_price', ''),
        'max_price': filters.get('max_price', ''),
        'ship_from': filters.get('ship_from', 'all'),
        'min_rating': filters.get('min_rating', ''),  # 🌟 ส่งค่าดาวที่เคยเลือกไว้ไปที่ HTML
        'ai_mode': filters.get('ai_mode', 'balanced'),
    }
    return render(request, 'dashboard.html', context)

# 8. ส่วนจัดการระบบสมาชิก (Admin)
@login_required
def manage_members_view(request):
    if not request.user.is_staff:
        raise PermissionDenied
    members = User.objects.filter(is_staff=False, is_superuser=False)
    return render(request, 'manage_members.html', {'members': members})

@login_required
def delete_member_view(request, user_id):
    if not request.user.is_staff:
        raise PermissionDenied
    if request.method == 'POST':
        member = get_object_or_404(User, id=user_id, is_staff=False, is_superuser=False)
        member.delete()
        messages.success(request, f"ลบบัญชีของ {member.first_name or member.username} สำเร็จแล้ว")
    return redirect('manage_members')

@login_required
def delete_history_view(request, history_id):
    if request.method == 'POST':
        history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
        history.delete()
    return redirect('history')


# myapp/views.py (นำไปต่อท้ายไฟล์ได้เลย)

@login_required
def compare_view(request):
    if request.method == 'POST':
        history_id = request.POST.get('history_id')
        selected_indexes = request.POST.getlist('selected_products') # จะได้เป็น List ['0', '3', '7']
        
        if len(selected_indexes) != 3:
            messages.error(request, 'กรุณาเลือกสินค้าให้ครบ 3 ชิ้น')
            return redirect(f'/dashboard/{history_id}/')

        # 1. ดึงข้อมูลประวัติการค้นหา
        history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
        parsed_data = json.loads(history.products_json)
        all_products = parsed_data.get('products', []) if isinstance(parsed_data, dict) else parsed_data
        
        # 2. คัดเฉพาะ 3 ชิ้นที่เลือก
        selected_products = []
        for idx in selected_indexes:
            selected_products.append(all_products[int(idx)])

        # ---------------------------------------------------------
        # 🌟 โซน Scrape เชิงลึก & AI (ทำงานตรงนี้)
        # ---------------------------------------------------------
        # (คุณสามารถเขียนโค้ด Selenium เพื่อให้บอทวิ่งเข้า URL ของ selected_products ทั้ง 3 ชิ้น 
        # เพื่อกวาด Description มาเก็บไว้ในตัวแปร และส่งให้ AI Gemini สรุปผลได้ที่นี่)
        
        ai_recommendation = "จากข้อมูลเชิงลึก สินค้าชิ้นที่ 1 มีความน่าเชื่อถือด้านการรับประกันที่ดีที่สุด ในขณะที่ชิ้นที่ 2 มีสเปคการใช้งานที่ตอบโจทย์ความคุ้มค่าด้านราคามากที่สุด หากคุณเน้นการใช้งานระยะยาว แนะนำให้เลือกชิ้นที่ 1 ครับ"
        
        context = {
            'keyword': history.keyword,
            'products': selected_products,
            'ai_recommendation': ai_recommendation
        }
        
        return render(request, 'compare.html', context)
        
    return redirect('search')