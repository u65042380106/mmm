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
from django.http import HttpResponse, JsonResponse 
import traceback
from django.db.models import Count
from myapp.models import SearchHistory, ComparisonRecord


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

def run_n8n_in_background(history_id, payload):
    try:
        history = SearchHistory.objects.get(id=history_id)
        history.status = 'pending_n8n'
        history.save()

        # ส่งไปหา n8n ทีเดียวให้จบกระบวนการทั้งหมด
        N8N_WEBHOOK_URL = 'http://localhost:5678/webhook-test/shopee-search'
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=None)
        
        if response.status_code == 200:
            result_data = response.json()
            
            # ตอนนี้เรารับข้อมูลที่มี image_url และ description สำเร็จรูปมาจาก n8n เลย
            products_9_items = result_data.get('products', [])
            ai_analysis = result_data.get('ai_analysis', 'ไม่มีผลวิเคราะห์')
            
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
            
            # ข้ามไปสถานะ success ได้เลย
            history.status = 'success' 
            history.save()
        else:
            history.status = 'error'
            history.ai_result = "n8n ตอบกลับด้วยสถานะ Error"
            history.save()
            
    except Exception as e:
        try:
            history = SearchHistory.objects.get(id=history_id)
            history.status = 'error'
            history.ai_result = "เกิดข้อผิดพลาดในการเชื่อมต่อระบบวิเคราะห์ข้อมูล"
            history.save()
            print(f"n8n Background Error: {e}")
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
        
        # ไปหน้า Loading ทันที
        return redirect('loading', history_id=history.id)
    except Exception as e:  
        return HttpResponse(f"Error: {e}")

@login_required
def history_view(request):
    histories = SearchHistory.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'history.html', {'histories': histories})

@login_required
def result_detail_view(request, history_id):
    history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
    
    # เช็กว่าประวัตินี้เคยมีการเปรียบเทียบไว้หรือยัง (ดึงอันล่าสุดมา)
    latest_comparison = history.comparisons.first()
    
    if latest_comparison:
        # ถ้าเคยเปรียบเทียบแล้ว พาไปดูหน้าผลลัพธ์การเปรียบเทียบล่าสุด
        return redirect('view_comparison', compare_id=latest_comparison.id)
    else:
        # ถ้ายังไม่เคยเปรียบเทียบเลย พาไปหน้าเลือกสินค้า
        return redirect('select_compare', history_id=history.id)

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

# --- โซนหน้า Loading ---
@login_required
def loading_view(request, history_id):
    history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
    return render(request, 'loading.html', {'history': history})

@login_required
def check_status_view(request, history_id):
    history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
    return JsonResponse({'status': history.status})

# --- โซน Compare ---
@login_required
def select_compare_view(request, history_id):
    history = get_object_or_404(SearchHistory, id=history_id, user=request.user)
    
    try:
        parsed_data = json.loads(history.products_json or '{}')
        if isinstance(parsed_data, dict):
            all_products = parsed_data.get('products', [])
        elif isinstance(parsed_data, list):
            all_products = parsed_data
        else:
            all_products = []
    except (json.JSONDecodeError, TypeError):
        all_products = []

    if request.method == 'POST':
        selected_indexes = request.POST.getlist('selected_products')
        
        if len(selected_indexes) < 2:
            messages.warning(request, 'กรุณาเลือกสินค้าอย่างน้อย 2 ชิ้นเพื่อทำการเปรียบเทียบ')
            return redirect('select_compare', history_id=history_id)
            
        if len(selected_indexes) > 4:
            messages.warning(request, 'เลือกเปรียบเทียบได้สูงสุด 4 ชิ้นเท่านั้น')
            return redirect('select_compare', history_id=history_id)

        try:
            selected_products = [all_products[int(idx)] for idx in selected_indexes]
        except (IndexError, ValueError):
            messages.error(request, 'เกิดข้อผิดพลาดในการเลือกสินค้า')
            return redirect('select_compare', history_id=history_id)

        ai_recommendation = "กำลังวิเคราะห์..."
        
        # 🌟 ส่งข้อมูลไปให้ n8n Workflow ตัวใหม่วิเคราะห์ 🌟
        try:
            # ⚠️ ตรวจสอบ URL Webhook ให้ตรงกับที่คุณตั้งใน n8n ⚠️
            N8N_COMPARE_WEBHOOK = 'http://localhost:5678/webhook/compare-items' 
            
            resp = requests.post(N8N_COMPARE_WEBHOOK, json={
                "keyword": history.keyword,
                "items": selected_products
            }, timeout=60) # เผื่อเวลาให้ AI คิด 60 วินาที
            
            if resp.status_code == 200:
                # พยายามโหลดผลลัพธ์ JSON ที่ AI ตอบกลับมา
                try:
                    result_data = resp.json()
                except json.JSONDecodeError:
                    result_data = json.loads(resp.text)
                
                ai_recommendation = result_data.get('recommendation', "การเปรียบเทียบเสร็จสิ้น")
                best_url = result_data.get('best_choice_url', "")
                
                # 🌟 ติดป้าย is_best_choice ให้สินค้าที่ AI เลือก 🌟
                for p in selected_products:
                    product_link = p.get('link', p.get('url', ''))
                    if product_link and product_link == best_url:
                        p['is_best_choice'] = True
                    else:
                        p['is_best_choice'] = False
            else:
                ai_recommendation = "ระบบ AI ขัดข้องชั่วคราว ไม่สามารถสร้างคำแนะนำได้"
        except Exception as e:
            print("N8N Error:", e)
            ai_recommendation = "ไม่สามารถเชื่อมต่อกับ AI N8N ได้ (ตรวจสอบ Webhook)"

        # บันทึกข้อมูลลงฐานข้อมูล
        new_comparison = ComparisonRecord.objects.create(
            history=history,
            selected_items_json=json.dumps(selected_products, ensure_ascii=False),
            ai_recommendation=ai_recommendation
        )
        
        return redirect('view_comparison', compare_id=new_comparison.id)

    return render(request, 'select_compare.html', {
        'keyword': history.keyword,
        'all_products': all_products,
        'history_id': history_id
    })

@login_required
def view_comparison_view(request, compare_id):
    comparison = get_object_or_404(ComparisonRecord, id=compare_id, history__user=request.user)
    
    try:
        selected_products = json.loads(comparison.selected_items_json)
    except:
        selected_products = []

    for item in selected_products:
        if isinstance(item, dict):
            item['product_url'] = item.get('link') or item.get('url') or ''

    return render(request, 'view_comparison.html', {
        'keyword': comparison.history.keyword,
        'selected_products': selected_products,
        'ai_recommendation': comparison.ai_recommendation,
        'history_id': comparison.history.id  # 🌟 ตรวจสอบว่าส่งชื่อนี้ออกไป
    })
