# scrape2.py
import time
from flask import Flask, jsonify, request
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

app = Flask(__name__)

def scrape_deep_details(urls):
    enriched_data = []
    
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--blink-settings=imagesEnabled=true") # ต้องโหลดภาพ
    
    try:
        driver = uc.Chrome(options=options, version_main=149)
        
        for url in urls:
            try:
                print(f"🔍 [Scrape2] กำลังเจาะลึก: {url}")
                driver.get(url)
                time.sleep(3) # รอให้หน้าเว็บโหลดสมบูรณ์
                
                # พยายามดึงรูปภาพความละเอียดสูง (รูปหลัก)
                high_res_image = ""
                try:
                    img_element = driver.find_element(By.CSS_SELECTOR, "img.pdp-mod-common-image.gallery-preview-panel__image")
                    high_res_image = img_element.get_attribute("src")
                    if high_res_image and high_res_image.startswith('//'):
                        high_res_image = 'https:' + high_res_image
                except: pass
                
                # พยายามดึงรายละเอียดสินค้า (Description)
                description = ""
                try:
                    desc_element = driver.find_element(By.CSS_SELECTOR, "div.html-content.pdp-product-highlights")
                    description = desc_element.text[:1000] # เก็บรายละเอียดคร่าวๆ 1000 ตัวอักษร
                except:
                    description = "ไม่มีรายละเอียดที่ดึงได้"

                enriched_data.append({
                    "url": url,
                    "high_res_image": high_res_image,
                    "description": description
                })
            except Exception as e:
                print(f"⚠️ Error เจาะลึก URL นี้: {url} -> {e}")
                enriched_data.append({"url": url, "high_res_image": "", "description": "Error"})
                
    except Exception as e:
        print(f"❌ Fatal Error in Scrape2: {e}")
    finally:
        try: driver.quit()
        except: pass
        
    return enriched_data

@app.route('/api/scrape_details', methods=['POST'])
def run_deep_scraper():
    data = request.get_json()
    urls = data.get('urls', [])
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400
        
    print(f"\n[API Scrape2] ได้รับคำสั่งเจาะลึกสินค้าจำนวน {len(urls)} ชิ้น")
    results = scrape_deep_details(urls)
    print("✅ เจาะลึกสำเร็จ ส่งข้อมูลกลับ...")
    return jsonify(results)

if __name__ == '__main__':
    print("🚀 สตาร์ท API เจาะลึกสินค้า 9 ชิ้น สแตนด์บายอยู่ที่พอร์ต 5001...")
    app.run(host='127.0.0.1', port=5001, debug=True)