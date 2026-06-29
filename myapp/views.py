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

def index_view(request):
    popular_searches = (
        SearchHistory.objects.values('keyword')
        .annotate(search_count=Count('keyword'))
        .order_by('-search_count')[:10]
    )
    return render(request, 'index.html', {'popular_searches': popular_searches})

@login_required
def search_view(request):
    return render(request, 'search.html')

@login_required
def profile_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        if username and username != request.user.username:
            if User.objects.filter(username=username).exists():
                messages.error(request, '❌ ชื่อผู้ใช้นี้มีคนใช้งานแล้ว')
                return redirect('profile')
            request.user.username = username
            
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save()
        messages.success(request, '✅ อัปเดตข้อมูลโปรไฟล์เรียบร้อยแล้ว!')
        return redirect('profile')
    return render(request, 'profile.html')

# แก้ไขเฉพาะฟังก์ชัน run_n8n_in_background
def run_n8n_in_background(history_id, payload):
    try:
        # ขั้นที่ 1: บอกว่ากำลังรอ AI และ Scrape 1 ทำงาน
        history = SearchHistory.objects.get(id=history_id)
        history.status = 'pending_n8n'
        history.save()

        N8N_WEBHOOK_URL = 'http://localhost:5678/webhook-test/shopee-search'
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=None)
        
        if response.status_code == 200:
            result_data = response.json()
            products_9_items = result_data.get('products', [])
            ai_analysis = result_data.get('ai_analysis', 'ไม่มีผลวิเคราะห์')
            
            # ขั้นที่ 2: ได้ของ 9 ชิ้นมาแล้ว บอกผู้ใช้ว่ากำลังรัน Scrape 2 (ดึงรูป)
            history.status = 'pending_scrape2'
            history.save()

            urls_to_scrape = [p.get('link') for p in products_9_items if p.get('link')]
            if urls_to_scrape:
                try:
                    scrape2_resp = requests.post('http://localhost:5001/api/scrape_details', json={'urls': urls_to_scrape})
                    if scrape2_resp.status_code == 200:
                        deep_details = scrape2_resp.json()
                        for product in products_9_items:
                            for detail in deep_details:
                                if product.get('link') == detail.get('url'):
                                    if detail.get('high_res_image'):
                                        product['image_url'] = detail['high_res_image']
                                    product['description'] = detail.get('description', '')
                except Exception as e:
                    print(f"Scrape2 Error: {e}") 

            history.ai_result = ai_analysis
            
            combined_data = {
                'products': products_9_items,
                'filters': {
                    'min_price': payload.get('min_price', ''),
                    'max_price': payload.get('max_price', ''),
                    'ship_from': payload.get('ship_from', 'all'),
                    'min_rating': payload.get('min_rating', ''),
                    'ai_mode': payload.get('ai_mode', 'balanced')
                }
            }
            history.products_json = json.dumps(combined_data, ensure_ascii=False)
            
            # ขั้นที่ 3: ทุกอย่างเสร็จสมบูรณ์ ปลดล็อคปุ่มให้เข้าไปดูผลลัพธ์ได้!
            history.status = 'success' 
            history.save()
            
    except Exception:
        try:
            history = SearchHistory.objects.get(id=history_id)
            history.status = 'error'
            history.ai_result = "เกิดข้อผิดพลาดในการเชื่อมต่อระบบวิเคราะห์ข้อมูล"
            history.save()
        except: pass

@login_required
def dashboard_view(request):
    try:  
        keyword = request.GET.get('keyword', '').strip()
        min_price = request.GET.get('min_price', '').strip()
        max_price = request.GET.get('max_price', '').strip()
        ship_from = request.GET.get('ship_from', 'all')
        min_rating = request.GET.get('min_rating', '').strip()
        ai_mode = request.GET.get('ai_mode', 'balanced')
        
        if not keyword: return redirect('search')
            
        ai_filter_parts = []
        # คำสั่งสำคัญ: บังคับคัดมาแค่ 9 ชิ้น!
        ai_filter_parts.append(f"โปรดวิเคราะห์ชื่อสินค้าเทียบกับ '{keyword}' คัดสแปมทิ้ง และ **คัดเลือกสินค้าที่ดีที่สุดมาให้เหลือเพียง 9 ชิ้นถ้วนเท่านั้น**")

        if min_price: ai_filter_parts.append(f"ราคาตั้งแต่ {min_price} บ.")
        if max_price: ai_filter_parts.append(f"ราคาไม่เกิน {max_price} บ.")
        if ship_from == 'local': ai_filter_parts.append("ส่งจากไทยเท่านั้น")
        elif ship_from == 'overseas': ai_filter_parts.append("ส่งจากต่างประเทศเท่านั้น")
        if min_rating: ai_filter_parts.append(f"รีวิวไม่ต่ำกว่า {min_rating} ดาว")

        if ai_mode == 'safe': ai_filter_parts.append("เน้นน่าเชื่อถือ รีวิวเยอะ")
        elif ai_mode == 'budget': ai_filter_parts.append("เน้นประหยัด คุ้มค่า")
        else: ai_filter_parts.append("จัดเรียงสมดุล ราคา/ความน่าเชื่อถือ")

        ai_filter_text = " และ ".join(ai_filter_parts)
            
        history = SearchHistory.objects.create(
            user=request.user, keyword=keyword, status='pending'
        )
        
        payload = {
            'keyword': keyword,
            'min_price': min_price, 'max_price': max_price,
            'ship_from': ship_from, 'min_rating': min_rating, 
            'ai_mode': ai_mode, 'ai_filter': ai_filter_text  
        }
        
        threading.Thread(target=run_n8n_in_background, args=(history.id, payload)).start()
        return redirect('history')
    except Exception as e:  
        return HttpResponse(f"Error: {e}")

@login_required
def history_view(request):
    histories = SearchHistory.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'history.html', {'histories': histories})

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
        'history_id': history.id,
        'min_price': filters.get('min_price', ''),
        'max_price': filters.get('max_price', ''),
        'ship_from': filters.get('ship_from', 'all'),
        'min_rating': filters.get('min_rating', ''),
        'ai_mode': filters.get('ai_mode', 'balanced'),
    }
    return render(request, 'dashboard.html', context)

@login_required
def manage_members_view(request):
    if not request.user.is_staff: raise PermissionDenied
    members = User.objects.filter(is_staff=False, is_superuser=False)
    return render(request, 'manage_members.html', {'members': members})

@login_required
def delete_member_view(request, user_id):
    if not request.user.is_staff: raise PermissionDenied
    if request.method == 'POST':
        member = get_object_or_404(User, id=user_id, is_staff=False, is_superuser=False)
        member.delete()
    return redirect('manage_members')

@login_required
def delete_history_view(request, history_id):
    if request.method == 'POST':
        history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
        history.delete()
    return redirect('history')

# 🚀 โซน Compare ของใหม่
@login_required
def compare_view(request):
    if request.method == 'POST':
        history_id = request.POST.get('history_id')
        selected_indexes = request.POST.getlist('selected_products') 
        
        if len(selected_indexes) != 3:
            messages.error(request, 'กรุณาเลือกสินค้าให้ครบ 3 ชิ้น')
            return redirect(f'/dashboard/{history_id}/')

        history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
        parsed_data = json.loads(history.products_json)
        all_products = parsed_data.get('products', []) if isinstance(parsed_data, dict) else parsed_data
        
        selected_products = [all_products[int(idx)] for idx in selected_indexes]

        # สร้าง Payload ส่งให้ AI วิเคราะห์เปรียบเทียบ 3 ชิ้น
        ai_recommendation = "กำลังวิเคราะห์..."
        try:
            # 🛠️ ส่งไปหา Webhook ของ n8n ตัวใหม่สำหรับ Compare (คุณต้องสร้าง webhook นี้ใน n8n ด้วย)
            N8N_COMPARE_WEBHOOK = 'http://localhost:5678/webhook/compare-items'
            resp = requests.post(N8N_COMPARE_WEBHOOK, json={
                "keyword": history.keyword,
                "items": selected_products
            }, timeout=15)
            
            if resp.status_code == 200:
                result = resp.json()
                ai_recommendation = result.get('recommendation', "เกิดข้อผิดพลาดในการดึงคำแนะนำ")
            else:
                ai_recommendation = "ระบบ AI ขัดข้องชั่วคราว ไม่สามารถสร้างคำแนะนำได้ในขณะนี้"
        except Exception:
            ai_recommendation = "ไม่สามารถเชื่อมต่อกับ AI N8N ได้ (กรุณาเช็กว่ารัน Webhook ไว้หรือไม่)"

        context = {
            'keyword': history.keyword,
            'products': selected_products,
            'ai_recommendation': ai_recommendation,
            'history_id': history_id # ส่งกลับไปเพื่อให้ปุ่มย้อนกลับทำงานได้ถูกต้อง
        }
        
        return render(request, 'compare.html', context)
        
    return redirect('search')