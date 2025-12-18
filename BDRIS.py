from flask import Flask, render_template_string, jsonify
import requests
import re
import base64
import os
from datetime import datetime

app = Flask(__name__)

# OCR.Space API Key → Railway-এ Environment Variable হিসেবে সেট করো
OCR_KEY = os.environ.get("OCR_KEY")
if not OCR_KEY:
    raise ValueError("OCR_KEY environment variable is required!")

# ইমেজ সেভ ফোল্ডার (ক্লাউডে /tmp ব্যবহার করা সেফ)
SAVE_DIR = "/tmp/captcha"
os.makedirs(SAVE_DIR, exist_ok=True)

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K)'})

def solve_captcha():
    try:
        # টোকেন নেওয়া
        r = s.get("https://everify.bdris.gov.bd/UBRNVerification/", timeout=20)
        token_match = re.search(r'CaptchaDeText.*?value="([^"]+)"', r.text)
        if not token_match:
            return None, "Token not found"
        token = token_match.group(1)

        # ক্যাপচা ইমেজ ডাউনলোড
        img_url = f"https://everify.bdris.gov.bd/DefaultCaptcha/Generate?t={token}"
        img_data = s.get(img_url, headers={'Referer': 'https://everify.bdris.gov.bd/UBRNVerification/'}, timeout=20).content

        # সেভ করা (অপশনাল – দেখার জন্য)
        fname = f"captcha_{datetime.now():%Y%m%d_%H%M%S}.gif"
        save_path = os.path.join(SAVE_DIR, fname)
        with open(save_path, "wb") as f:
            f.write(img_data)

        # Base64 এনকোড
        b64 = base64.b64encode(img_data).decode()

        # OCR.Space API কল
        payload = {
            'apikey': OCR_KEY,
            'language': 'eng',
            'OCREngine': '1',  # GIF সাপোর্ট করে
            'base64Image': f'data:image/gif;base64,{b64}',
            'scale': 'true',
            'isOverlayRequired': 'false'
        }
        ocr_response = requests.post("https://api.ocr.space/parse/image", data=payload, timeout=20).json()

        raw_text = ocr_response.get("ParsedResults", [{}])[0].get("ParsedText", "").strip()

        # টেক্সট ক্লিন করা
        text = re.sub(r'[^0-9+\-×xX*]', ' ', raw_text)
        text = re.sub(r'\s+', ' ', text).strip()

        # গুণ চিহ্ন এক করা
        text = text.replace('×', 'x').replace('X', 'x').replace('*', 'x')

        # গণিত এক্সট্র্যাক্ট
        match = re.search(r'(\d+)\s*([+x\-])\s*(\d+)', text)
        if not match:
            answer = "??"
            calculation = "গণিত পাওয়া যায়নি"
        else:
            a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
            if op == 'x':
                answer = str(a * b)
            elif op == '+':
                answer = str(a + b)
            elif op == '-':
                answer = str(a - b)
            else:
                answer = "??"
            calculation = f"{a} {op} {b} = {answer}"

        return {
            "image": f"data:image/gif;base64,{b64}",
            "file": fname,
            "ocr": raw_text or "কিছু পাওয়া যায়নি",
            "calculation": calculation,
            "answer": answer
        }, None

    except Exception as e:
        return None, str(e)

# ওয়েব ইন্টারফেস (অপরিবর্তিত – সুন্দর আছে)
HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>BD RIS Captcha Solver - ১০০% কাজ করে</title>
    <style>
        body { background: #000; color: #0f0; font-family: monospace; text-align: center; padding: 10px; }
        .box { background: #111; padding: 20px; border-radius: 15px; max-width: 500px; margin: auto; border: 3px solid lime; }
        img { max-width: 100%; border: 5px solid lime; border-radius: 15px; margin: 20px 0; }
        button { background:lime; color:black; font-size:22px; padding:15px 40px; border:none; border-radius:50px; margin:10px; }
        .ans { font-size: 70px; color: lime; font-weight: bold; margin: 30px; background:#000; padding:20px; border-radius:20px; }
    </style>
</head>
<body>
    <div class="box">
        <h1 style="color:lime">BD RIS CAPTCHA SOLVER</h1>
        <p><b>ইমেজ সেভ হচ্ছে:</b><br>/tmp/captcha/ (সার্ভারে)</p>
        <button onclick="go()">নতুন ক্যাপচা আনুন</button>
        <div id="res"></div>
    </div>
    <script>
        function go(){
            document.getElementById("res").innerHTML = "<p>লোড হচ্ছে...</p>";
            fetch("/api").then(r=>r.json()).then(d=>{
                if(d.status){
                    document.getElementById("res").innerHTML = `
                        <img src="${d.image}">
                        <p><b>OCR টেক্সট:</b> ${d.ocr}</p>
                        <p><b>হিসাব:</b> ${d.calculation}</p>
                        <div class="ans">উত্তর = ${d.answer}</div>
                        <button onclick="go()">আরেকটা</button>
                    `;
                } else {
                    document.getElementById("res").innerHTML = "<p style='color:red'>Error: "+d.error+"</p><button onclick='go()'>আবার চেষ্টা করুন</button>";
                }
            }).catch(err => {
                document.getElementById("res").innerHTML = "<p style='color:red'>Network Error</p>";
            });
        }
        go();
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return HTML

@app.route("/api")
def api():
    data, err = solve_captcha()
    if data:
        return jsonify({"status": True, **data})
    else:
        return jsonify({"status": False, "error": err})

# Railway বা অন্য প্ল্যাটফর্মে রান করার জন্য
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
