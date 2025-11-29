from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from kerykeion import AstrologicalSubject, KerykeionChartSVG
from datetime import datetime
import traceback
import os
from functools import lru_cache
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- CONFIGURATION ---
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
LLM_MODEL = "llama-3.3-70b-versatile"

# --- LLM SETUP ---
try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY)
    LLM_AVAILABLE = True
except:
    groq_client = None
    LLM_AVAILABLE = False

def call_llm(system_prompt, user_prompt, max_tokens=2500):
    if not LLM_AVAILABLE or not groq_client:
        return None
    try:
        completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=LLM_MODEL,
            temperature=0.7,
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"LLM Error: {e}")
        return None

@lru_cache(maxsize=100)
def get_location_data(city_name):
    FALLBACK_CITIES = {
        'delhi': {'lat': 28.6139, 'lng': 77.2090, 'tz': 'Asia/Kolkata'},
        'mumbai': {'lat': 19.0760, 'lng': 72.8777, 'tz': 'Asia/Kolkata'},
        'bangalore': {'lat': 12.9716, 'lng': 77.5946, 'tz': 'Asia/Kolkata'},
        'new york': {'lat': 40.7128, 'lng': -74.0060, 'tz': 'America/New_York'},
        'london': {'lat': 51.5074, 'lng': -0.1278, 'tz': 'Europe/London'},
    }
    clean_name = city_name.lower().strip()
    if clean_name in FALLBACK_CITIES:
        data = FALLBACK_CITIES[clean_name]
        data['city'] = city_name.title()
        return data

    try:
        geolocator = Nominatim(user_agent="astro_luxury_app_v5", timeout=10)
        location = geolocator.geocode(city_name)
        if location:
            tf = TimezoneFinder()
            tz_str = tf.timezone_at(lng=location.longitude, lat=location.latitude)
            return {
                'lat': location.latitude,
                'lng': location.longitude,
                'tz': tz_str or 'UTC',
                'city': location.address.split(",")[0]
            }
    except Exception as e:
        print(f"Geo Error: {e}")
    
    return {'lat': 40.7128, 'lng': -74.0060, 'tz': 'America/New_York', 'city': 'New York'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chart', methods=['POST'])
def generate_chart():
    try:
        data = request.json
        loc = get_location_data(data.get('city', 'New York'))
        
        # 1. User's Natal Chart
        user = AstrologicalSubject(
            name=data.get('name', 'User'),
            year=int(data['year']),
            month=int(data['month']),
            day=int(data['day']),
            hour=int(data['hour']),
            minute=int(data['minute']),
            city=loc['city'],
            lat=loc['lat'],
            lng=loc['lng'],
            tz_str=loc['tz']
        )
        
        # 2. Current Transits
        now = datetime.now()
        sky_now = AstrologicalSubject("Now", now.year, now.month, now.day, now.hour, now.minute, lng=loc['lng'], lat=loc['lat'], tz_str=loc['tz'])
        
        # 3. MEGA PROMPT for Full Analysis
        system_prompt = """
        You are a celebrity astrologer for a luxury magazine.
        Write a comprehensive "Book of You" analysis.
        Tone: Psychological, Empowering, Elegant. No cheesy newspaper horoscopes.
        """
        
        prompt = f"""
        USER CHART:
        Sun: {user.sun.sign}, Moon: {user.moon.sign}, Rising: {user.first_house.sign}
        Venus: {user.venus.sign}, Mars: {user.mars.sign}, Jupiter: {user.jupiter.sign}
        
        CURRENT TRANSITS:
        Sun: {sky_now.sun.sign}, Moon: {sky_now.moon.sign}, Saturn: {sky_now.saturn.sign}

        Provide analysis in these EXACT SECTIONS (do not use markdown bolding **):

        SECTION_PERSONALITY:
        (150 words. Describe their core character based on Sun/Moon/Rising blend. Deep psychological insight.)

        SECTION_LOVE:
        (100 words. Analyze Venus sign. How do they love? What partner suits them?)

        SECTION_CAREER:
        (100 words. Analyze Mars and Saturn. Their work style and path to success.)

        SECTION_FUTURE:
        (150 words. A predictive look at the next 6 months based on current Transits. What is the major theme?)

        SECTION_LIFE_PATH:
        (50 words. A spiritual summary of their life's purpose.)

        SECTION_LUCKY_NUMBER:
        (Just the number, e.g., "7")

        SECTION_LUCKY_COLOR:
        (Just the color name, e.g., "Emerald Green")
        """
        
        analysis = call_llm(system_prompt, prompt, 2500)
        
        # Parse Response
        results = {
            "personality": "", "love": "", "career": "", 
            "future": "", "life": "", "number": "7", "color": "Gold"
        }
        
        if analysis:
            current_section = None
            for line in analysis.split('\n'):
                line = line.strip()
                if "SECTION_PERSONALITY:" in line: current_section = "personality"
                elif "SECTION_LOVE:" in line: current_section = "love"
                elif "SECTION_CAREER:" in line: current_section = "career"
                elif "SECTION_FUTURE:" in line: current_section = "future"
                elif "SECTION_LIFE_PATH:" in line: current_section = "life"
                elif "SECTION_LUCKY_NUMBER:" in line: current_section = "number"
                elif "SECTION_LUCKY_COLOR:" in line: current_section = "color"
                
                elif current_section and line:
                    clean_line = line.replace("SECTION_", "").replace(":", "") # Cleanup
                    if current_section in ["number", "color"]:
                        results[current_section] = clean_line 
                    else:
                        results[current_section] += clean_line + " "

        return jsonify({
            'success': True,
            'data': {
                'sun': user.sun.sign,
                'moon': user.moon.sign,
                'rising': user.first_house.sign,
                'analysis': results
            }
        })

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

