from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import uvicorn
import os
import sys
import traceback

# إنشاء التطبيق
app = FastAPI(title="Image Processor API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# تحميل rembg بشكل آمن مع معالجة الأخطاء
try:
    from rembg import remove, new_session
    from PIL import Image, ImageFilter, ImageOps, ImageEnhance
    
    # استخدام نموذج خفيف لتقليل استهلاك الذاكرة
    # u2net أخف من u2net_human_seg
    MODEL_NAME = "u2net"
    
    # تحميل النموذج مرة واحدة عند بدء التشغيل
    print("⏳ جاري تحميل نموذج إزالة الخلفية...")
    session = new_session(MODEL_NAME)
    print(f"✅ تم تحميل النموذج {MODEL_NAME} بنجاح!")
    
    REMBG_AVAILABLE = True
    
except Exception as e:
    print(f"⚠️ فشل تحميل rembg: {str(e)}")
    print("🔧 سيتم استخدام معالجة بديلة بدون إزالة خلفية")
    traceback.print_exc()
    REMBG_AVAILABLE = False


def process_image_local(product_bytes: bytes, logo_bytes: bytes) -> bytes:
    """معالجة الصورة مع إزالة الخلفية إن أمكن"""
    
    # فتح الصور
    input_image = Image.open(io.BytesIO(product_bytes)).convert("RGBA")
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    
    if REMBG_AVAILABLE:
        try:
            # إزالة الخلفية باستخدام rembg
            cutout = remove(input_image, session=session).convert("RGBA")
        except Exception as e:
            print(f"خطأ في rembg: {e}")
            # استخدام الصورة كما هي إذا فشلت إزالة الخلفية
            cutout = input_image
    else:
        # إذا لم تكن rembg متاحة، استخدم الصورة الأصلية
        cutout = input_image
    
    # خلفية بيضاء
    white_bg = Image.new("RGBA", cutout.size, (255, 255, 255, 255))
    combined = Image.alpha_composite(white_bg, cutout)
    
    try:
        # ظل احترافي
        shadow = cutout.copy().convert("L").filter(ImageFilter.GaussianBlur(12))
        shadow = ImageOps.colorize(shadow, black="black", white="white").convert("RGBA")
        shadow_bg = Image.new("RGBA", combined.size, (255, 255, 255, 0))
        shadow_bg.paste(shadow, (8, 15), shadow)
        final_image = Image.alpha_composite(shadow_bg, combined)
    except:
        final_image = combined
    
    # إضافة الشعار
    img_w, img_h = final_image.size
    logo_size = int(img_w * 0.1)
    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
    
    try:
        alpha = logo.split()[-1]
        alpha = ImageEnhance.Brightness(alpha).enhance(0.6)
        logo.putalpha(alpha)
    except:
        pass
    
    margin = int(img_w * 0.03)
    pos_x = img_w - logo.size[0] - margin
    pos_y = img_h - logo.size[1] - margin
    
    final_image.paste(logo, (pos_x, pos_y), logo)
    final_image = final_image.convert("RGB")
    
    # تحويل إلى bytes
    img_bytes = io.BytesIO()
    final_image.save(img_bytes, format="PNG", optimize=True)
    img_bytes.seek(0)
    
    return img_bytes.getvalue()


@app.on_event("startup")
async def startup_event():
    """يتم تنفيذه عند بدء التشغيل"""
    print("🚀 بدء تشغيل Image Processor API")
    print(f"📦 RemBG متاح: {REMBG_AVAILABLE}")
    print(f"💾 الذاكرة المتاحة: للتحقق...")


@app.get("/")
async def root():
    """نقطة البداية - للتحقق من عمل الخدمة"""
    return {
        "status": "online",
        "service": "Image Processor API",
        "version": "1.0.0",
        "rembg_available": REMBG_AVAILABLE,
        "endpoints": {
            "process": "/process (POST)",
            "health": "/health (GET)",
            "docs": "/docs (GET)"
        }
    }


@app.get("/health")
async def health():
    """فحص صحة الخدمة"""
    import psutil
    memory = psutil.virtual_memory()
    
    return {
        "status": "healthy",
        "rembg_available": REMBG_AVAILABLE,
        "memory_used_percent": memory.percent,
        "memory_available_mb": memory.available // (1024 * 1024)
    }


@app.post("/process")
async def process_endpoint(
    product: UploadFile = File(...),
    logo: UploadFile = File(...)
):
    """معالجة الصورة"""
    
    if not product.content_type or not product.content_type.startswith("image/"):
        raise HTTPException(400, "الملف الأول يجب أن يكون صورة")
    if not logo.content_type or not logo.content_type.startswith("image/"):
        raise HTTPException(400, "الملف الثاني يجب أن يكون صورة")
    
    try:
        # قراءة الملفات
        product_bytes = await product.read()
        logo_bytes = await logo.read()
        
        # التحقق من حجم الملفات (بحد أقصى 10 ميجا)
        max_size = 10 * 1024 * 1024  # 10MB
        if len(product_bytes) > max_size:
            raise HTTPException(400, "حجم صورة المنتج كبير جداً (الحد الأقصى 10 ميجابايت)")
        if len(logo_bytes) > max_size:
            raise HTTPException(400, "حجم الشعار كبير جداً (الحد الأقصى 10 ميجابايت)")
        
        # معالجة الصورة
        result = process_image_local(product_bytes, logo_bytes)
        
        # إرجاع النتيجة
        return StreamingResponse(
            io.BytesIO(result),
            media_type="image/png",
            headers={"Content-Disposition": "inline; filename=result.png"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"خطأ في المعالجة: {str(e)}")
    finally:
        await product.close()
        await logo.close()


# هذا مهم جداً لـ Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)