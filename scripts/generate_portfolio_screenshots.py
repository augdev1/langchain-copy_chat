import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent
PORTFOLIO_DIR = BASE_DIR / "portfolio"
PORTFOLIO_DIR.mkdir(exist_ok=True)

# Shared CSS for WhatsApp Chat Mockups & Fiverr Presentation Cards
SHARED_STYLES = """
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

body {
    width: 1920px;
    height: 1080px;
    background: radial-gradient(circle at 20% 20%, #0f172a 0%, #020617 100%);
    color: #f8fafc;
    display: flex;
    justify-content: center;
    align-items: center;
    overflow: hidden;
    position: relative;
}

/* Ambient glow */
.ambient-glow {
    position: absolute;
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0) 70%);
    top: -100px;
    left: -100px;
    filter: blur(80px);
    pointer-events: none;
}

.ambient-glow-2 {
    position: absolute;
    width: 700px;
    height: 700px;
    background: radial-gradient(circle, rgba(59, 130, 246, 0.12) 0%, rgba(59, 130, 246, 0) 70%);
    bottom: -150px;
    right: -150px;
    filter: blur(90px);
    pointer-events: none;
}

/* Phone Mockup Frame */
.phone-frame {
    width: 440px;
    height: 920px;
    background: #0b141a;
    border-radius: 54px;
    box-shadow: 
        0 0 0 12px #1e293b,
        0 0 0 14px #334155,
        0 30px 60px -12px rgba(0, 0, 0, 0.7),
        0 0 50px rgba(16, 185, 129, 0.2);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
    border: 3px solid rgba(255, 255, 255, 0.1);
}

/* iPhone Dynamic Island & Status Bar */
.phone-status-bar {
    height: 48px;
    padding: 12px 28px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 14px;
    font-weight: 600;
    color: #ffffff;
    background: #111b21;
    z-index: 10;
}

.dynamic-island {
    width: 110px;
    height: 26px;
    background: #000000;
    border-radius: 18px;
    position: absolute;
    top: 10px;
    left: 50%;
    transform: translateX(-50%);
}

/* WhatsApp Header */
.wa-header {
    height: 64px;
    background: #111b21;
    display: flex;
    align-items: center;
    padding: 0 16px;
    gap: 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    z-index: 5;
}

.wa-avatar-box {
    position: relative;
    width: 42px;
    height: 42px;
}

.wa-avatar {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    background: linear-gradient(135deg, #10b981, #047857);
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: 20px;
    font-weight: bold;
    color: #fff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.verified-badge {
    position: absolute;
    bottom: -2px;
    right: -2px;
    background: #10b981;
    color: #fff;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    border: 2px solid #111b21;
}

.wa-user-info {
    flex: 1;
}

.wa-user-name {
    font-size: 16px;
    font-weight: 600;
    color: #e9edef;
    display: flex;
    align-items: center;
    gap: 6px;
}

.wa-status {
    font-size: 12px;
    color: #10b981;
    font-weight: 500;
}

/* WhatsApp Chat Area */
.wa-chat-area {
    flex: 1;
    background-color: #0b141a;
    background-image: radial-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
    background-size: 20px 20px;
    padding: 16px 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
}

/* WhatsApp Date Divider */
.wa-date-divider {
    align-self: center;
    background: #182229;
    color: #8696a0;
    font-size: 11px;
    font-weight: 600;
    padding: 5px 12px;
    border-radius: 8px;
    text-transform: uppercase;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}

/* Bubbles */
.wa-bubble {
    max-width: 88%;
    padding: 9px 12px 6px 12px;
    border-radius: 12px;
    font-size: 13.5px;
    line-height: 1.45;
    position: relative;
    word-wrap: break-word;
    box-shadow: 0 1px 1px rgba(0,0,0,0.15);
}

.wa-bubble.incoming {
    align-self: flex-start;
    background: #202c33;
    color: #e9edef;
    border-top-left-radius: 2px;
}

.wa-bubble.outgoing {
    align-self: flex-end;
    background: #005c4b;
    color: #e9edef;
    border-top-right-radius: 2px;
}

.wa-bubble strong {
    color: #ffffff;
    font-weight: 700;
}

.wa-bubble em {
    color: #94a3b8;
    font-style: italic;
}

.wa-bubble-meta {
    float: right;
    margin-left: 10px;
    margin-top: 4px;
    font-size: 10.5px;
    color: #8696a0;
    display: flex;
    align-items: center;
    gap: 3px;
}

.wa-checkmarks {
    color: #53bdeb;
    font-size: 13px;
    font-weight: bold;
}

/* Bottom Bar */
.wa-input-bar {
    height: 60px;
    background: #202c33;
    display: flex;
    align-items: center;
    padding: 0 12px;
    gap: 10px;
}

.wa-input-pill {
    flex: 1;
    height: 38px;
    background: #2a3942;
    border-radius: 20px;
    padding: 0 16px;
    color: #8696a0;
    font-size: 13.5px;
    display: flex;
    align-items: center;
}

.wa-mic-btn {
    width: 38px;
    height: 38px;
    background: #00a884;
    border-radius: 50%;
    display: flex;
    justify-content: center;
    align-items: center;
    color: #fff;
    font-size: 16px;
}
"""

SLIDE_1_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
{SHARED_STYLES}

.container {{
    width: 1720px;
    height: 940px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    z-index: 2;
}}

/* Left Info Content */
.info-content {{
    flex: 1;
    max-width: 960px;
    display: flex;
    flex-direction: column;
    gap: 24px;
}}

.fiverr-badge {{
    align-self: flex-start;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 18px;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 999px;
    color: #34d399;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

.fiverr-badge span {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 10px #10b981;
}}

h1.main-title {{
    font-size: 58px;
    font-weight: 900;
    line-height: 1.1;
    background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 60%, #94a3b8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}

h1.main-title .highlight {{
    background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}

p.subtitle {{
    font-size: 20px;
    color: #94a3b8;
    line-height: 1.5;
    max-width: 860px;
}}

/* Grid of features */
.feature-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-top: 8px;
}}

.feature-card {{
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 18px 20px;
    display: flex;
    align-items: flex-start;
    gap: 14px;
    backdrop-filter: blur(12px);
}}

.feature-icon {{
    width: 44px;
    height: 44px;
    border-radius: 12px;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(59, 130, 246, 0.2));
    border: 1px solid rgba(255, 255, 255, 0.1);
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: 22px;
    flex-shrink: 0;
}}

.feature-text h3 {{
    font-size: 17px;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 4px;
}}

.feature-text p {{
    font-size: 13.5px;
    color: #94a3b8;
    line-height: 1.4;
}}

/* Tech Stack Banner */
.tech-banner {{
    display: flex;
    align-items: center;
    gap: 18px;
    margin-top: 10px;
    padding-top: 18px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}}

.tech-label {{
    font-size: 12.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #64748b;
}}

.tech-pills {{
    display: flex;
    gap: 10px;
}}

.tech-pill {{
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 12.5px;
    font-weight: 600;
    color: #cbd5e1;
}}
</style>
</head>
<body>
<div class="ambient-glow"></div>
<div class="ambient-glow-2"></div>

<div class="container">
    <div class="info-content">
        <div class="fiverr-badge">
            <span></span> WhatsApp API Integration & AI Architecture
        </div>
        
        <h1 class="main-title">
            Autonomous <span class="highlight">WhatsApp AI Bot</span> with LangChain & LangGraph
        </h1>
        
        <p class="subtitle">
            An enterprise-grade, stateful AI assistant that automates user conversations, manages multi-step workflows, and delivers instant structured copy via WhatsApp webhooks.
        </p>

        <div class="feature-grid">
            <div class="feature-card">
                <div class="feature-icon">🧠</div>
                <div class="feature-text">
                    <h3>LangGraph State Machine</h3>
                    <p>Stateful multi-turn memory, resilient execution branches, and automatic conversational routing.</p>
                </div>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">⚡</div>
                <div class="feature-text">
                    <h3>Gemini 3.8 Flash API Engine</h3>
                    <p>Sub-second generation latency, structured output parsing, and dynamic contextual system prompts.</p>
                </div>
            </div>

            <div class="feature-card">
                <div class="feature-icon">📱</div>
                <div class="feature-text">
                    <h3>WhatsApp Webhook Integration</h3>
                    <p>Bi-directional webhook synchronization, message status events, and zero-latency replies.</p>
                </div>
            </div>

            <div class="feature-card">
                <div class="feature-icon">🛡️</div>
                <div class="feature-text">
                    <h3>Production Concurrency & Redis</h3>
                    <p>Distributed Redis locks by phone number, message deduplication, and PostgreSQL RAG vector persistence.</p>
                </div>
            </div>
        </div>

        <div class="tech-banner">
            <div class="tech-label">Architecture:</div>
            <div class="tech-pills">
                <div class="tech-pill">LangChain</div>
                <div class="tech-pill">LangGraph</div>
                <div class="tech-pill">Google Gemini 3.8</div>
                <div class="tech-pill">FastAPI</div>
                <div class="tech-pill">Redis 7</div>
                <div class="tech-pill">Docker</div>
            </div>
        </div>
    </div>

    <!-- Phone Mockup -->
    <div class="phone-frame">
        <div class="dynamic-island"></div>
        <div class="phone-status-bar">
            <span>9:41</span>
            <span>5G 􀛨 100%</span>
        </div>

        <div class="wa-header">
            <div class="wa-avatar-box">
                <div class="wa-avatar">🤖</div>
                <div class="verified-badge">✓</div>
            </div>
            <div class="wa-user-info">
                <div class="wa-user-name">CopyBot AI <span style="color:#10b981;font-size:13px;">✔</span></div>
                <div class="wa-status">online</div>
            </div>
        </div>

        <div class="wa-chat-area">
            <div class="wa-date-divider">Today</div>

            <div class="wa-bubble incoming">
                Hello! 👋 I'm your <strong>AI Copywriting & Strategy Assistant</strong>.<br><br>
                To calibrate your brand voice and context, please provide your <strong>brand handle or Instagram username</strong>:
                <div class="wa-bubble-meta">09:41</div>
            </div>

            <div class="wa-bubble outgoing">
                @rodrigofitness
                <div class="wa-bubble-meta">09:41 <span class="wa-checkmarks">✓✓</span></div>
            </div>

            <div class="wa-bubble incoming">
                Perfect, Rodrigo! 🚀<br><br>
                Which content format would you like to create today?<br><br>
                1️⃣ <strong>STORIES</strong> (Lead Conversion)<br>
                2️⃣ <strong>FEED</strong> (Carousel / Single Post)<br>
                3️⃣ <strong>REELS</strong> (Video Script)<br>
                4️⃣ <strong>WHATSAPP LEAD</strong> (Direct Sales Pitch)
                <div class="wa-bubble-meta">09:42</div>
            </div>

            <div class="wa-bubble outgoing">
                1
                <div class="wa-bubble-meta">09:42 <span class="wa-checkmarks">✓✓</span></div>
            </div>

            <div class="wa-bubble incoming">
                Great choice! 🎯<br><br>
                What is the core topic or pain point you want to address?<br><br>
                <em>(e.g., prospects working out 6x/week but struggling with muscle definition)</em>
                <div class="wa-bubble-meta">09:42</div>
            </div>
        </div>

        <div class="wa-input-bar">
            <div class="wa-input-pill">Type a message...</div>
            <div class="wa-mic-btn">➤</div>
        </div>
    </div>
</div>
</body>
</html>
"""

SLIDE_2_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
{SHARED_STYLES}

.header-banner {{
    position: absolute;
    top: 40px;
    left: 100px;
    right: 100px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    padding-bottom: 20px;
    z-index: 10;
}}

.header-title-box h2 {{
    font-size: 32px;
    font-weight: 800;
    color: #ffffff;
}}

.header-title-box p {{
    font-size: 16px;
    color: #94a3b8;
    margin-top: 4px;
}}

.step-indicator {{
    display: flex;
    gap: 12px;
}}

.step-pill {{
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 8px 16px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 600;
    color: #94a3b8;
    display: flex;
    align-items: center;
    gap: 8px;
}}

.step-pill.active {{
    background: rgba(16, 185, 129, 0.2);
    border-color: #10b981;
    color: #34d399;
}}

/* Triple Phone Layout */
.phones-container {{
    margin-top: 80px;
    display: flex;
    gap: 40px;
    align-items: center;
    z-index: 2;
}}

.phone-card {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
}}

.phone-label {{
    font-size: 15px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.12);
    padding: 6px 16px;
    border-radius: 20px;
    border: 1px solid rgba(56, 189, 248, 0.25);
}}

.phone-frame.compact {{
    width: 380px;
    height: 740px;
    border-radius: 44px;
}}
</style>
</head>
<body>
<div class="ambient-glow"></div>
<div class="ambient-glow-2"></div>

<div class="header-banner">
    <div class="header-title-box">
        <h2>Interactive State Machine & Decision Architecture</h2>
        <p>Zero cognitive friction: The bot guides users through validation, format selection, and briefing capture.</p>
    </div>
    <div class="step-indicator">
        <div class="step-pill">1. Brand Identity</div>
        <div class="step-pill active">2. Smart Intent Extraction</div>
        <div class="step-pill">3. Copy Synthesis</div>
    </div>
</div>

<div class="phones-container">
    <!-- Step 1 Phone -->
    <div class="phone-card">
        <div class="phone-label">Stage 1 • Brand Calibration</div>
        <div class="phone-frame compact">
            <div class="dynamic-island" style="width: 90px; height: 22px;"></div>
            <div class="phone-status-bar" style="height: 40px; font-size: 12px;">
                <span>09:40</span>
                <span>5G 􀛨 100%</span>
            </div>
            <div class="wa-header" style="height: 56px;">
                <div class="wa-avatar" style="width: 36px; height: 36px; font-size: 17px;">🤖</div>
                <div class="wa-user-info">
                    <div class="wa-user-name" style="font-size: 14px;">CopyBot AI</div>
                    <div class="wa-status" style="font-size: 11px;">online</div>
                </div>
            </div>
            <div class="wa-chat-area" style="font-size: 12.5px;">
                <div class="wa-bubble incoming">
                    Hello! Welcome to the <strong>Copywriting Assistant Engine</strong>.<br><br>
                    To calibrate your brand voice, please enter your Instagram handle:
                    <div class="wa-bubble-meta">09:40</div>
                </div>
                <div class="wa-bubble outgoing">
                    @julianamarketing
                    <div class="wa-bubble-meta">09:40 <span class="wa-checkmarks">✓✓</span></div>
                </div>
                <div class="wa-bubble incoming">
                    Great, Juliana! Brand profile calibrated successfully. ✨
                    <div class="wa-bubble-meta">09:41</div>
                </div>
            </div>
            <div class="wa-input-bar" style="height: 50px;">
                <div class="wa-input-pill" style="height: 32px; font-size: 12px;">Type a message...</div>
            </div>
        </div>
    </div>

    <!-- Step 2 Phone -->
    <div class="phone-card">
        <div class="phone-label" style="color: #34d399; border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.12);">Stage 2 • Multi-Format Menu</div>
        <div class="phone-frame compact" style="box-shadow: 0 0 0 12px #10b98133, 0 25px 50px rgba(0,0,0,0.8);">
            <div class="dynamic-island" style="width: 90px; height: 22px;"></div>
            <div class="phone-status-bar" style="height: 40px; font-size: 12px;">
                <span>09:41</span>
                <span>5G 􀛨 100%</span>
            </div>
            <div class="wa-header" style="height: 56px;">
                <div class="wa-avatar" style="width: 36px; height: 36px; font-size: 17px;">🤖</div>
                <div class="wa-user-info">
                    <div class="wa-user-name" style="font-size: 14px;">CopyBot AI</div>
                    <div class="wa-status" style="font-size: 11px;">typing...</div>
                </div>
            </div>
            <div class="wa-chat-area" style="font-size: 12.5px;">
                <div class="wa-bubble incoming">
                    Select your desired format:<br><br>
                    1️⃣ <strong>STORIES</strong><br>
                    2️⃣ <strong>FEED</strong> (Carousel / Post)<br>
                    3️⃣ <strong>REELS</strong><br>
                    4️⃣ <strong>WHATSAPP LEAD</strong>
                    <div class="wa-bubble-meta">09:41</div>
                </div>
                <div class="wa-bubble outgoing">
                    2
                    <div class="wa-bubble-meta">09:41 <span class="wa-checkmarks">✓✓</span></div>
                </div>
                <div class="wa-bubble incoming">
                    Selected format: <strong>FEED</strong>.<br><br>
                    Would you like an <strong>Authority Carousel</strong> or a <strong>Single Post with High-Impact Caption</strong>?
                    <div class="wa-bubble-meta">09:42</div>
                </div>
            </div>
            <div class="wa-input-bar" style="height: 50px;">
                <div class="wa-input-pill" style="height: 32px; font-size: 12px;">Type a message...</div>
            </div>
        </div>
    </div>

    <!-- Step 3 Phone -->
    <div class="phone-card">
        <div class="phone-label" style="color: #a855f7; border-color: rgba(168, 85, 247, 0.3); background: rgba(168, 85, 247, 0.12);">Stage 3 • Smart Intent Bypass</div>
        <div class="phone-frame compact">
            <div class="dynamic-island" style="width: 90px; height: 22px;"></div>
            <div class="phone-status-bar" style="height: 40px; font-size: 12px;">
                <span>09:43</span>
                <span>5G 􀛨 100%</span>
            </div>
            <div class="wa-header" style="height: 56px;">
                <div class="wa-avatar" style="width: 36px; height: 36px; font-size: 17px;">🤖</div>
                <div class="wa-user-info">
                    <div class="wa-user-name" style="font-size: 14px;">CopyBot AI</div>
                    <div class="wa-status" style="font-size: 11px;">online</div>
                </div>
            </div>
            <div class="wa-chat-area" style="font-size: 12.5px;">
                <div class="wa-bubble outgoing">
                    I want a post about why audience size doesn't guarantee sales and how to build mental territory instead of vanity metrics.
                    <div class="wa-bubble-meta">09:43 <span class="wa-checkmarks">✓✓</span></div>
                </div>
                <div class="wa-bubble incoming">
                    🎯 <strong>Smart Intent Detected!</strong><br><br>
                    Identified objective: <em>Authority Repositioning & Vanity Metric Breakdown</em>.<br><br>
                    Generating your copy via <strong>Gemini 3.8 Flash API</strong> with system guidelines... ⏳
                    <div class="wa-bubble-meta">09:43</div>
                </div>
            </div>
            <div class="wa-input-bar" style="height: 50px;">
                <div class="wa-input-pill" style="height: 32px; font-size: 12px;">Type a message...</div>
            </div>
        </div>
    </div>
</div>
</body>
</html>
"""

SLIDE_3_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
{SHARED_STYLES}

.container {{
    width: 1720px;
    height: 940px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    z-index: 2;
}}

/* Left Output Mockup (Wider WhatsApp View) */
.phone-frame.wide {{
    width: 520px;
    height: 920px;
    border-radius: 54px;
}}

/* Right Features */
.right-panel {{
    flex: 1;
    max-width: 980px;
    display: flex;
    flex-direction: column;
    gap: 28px;
}}

.section-tag {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #f59e0b;
    background: rgba(245, 158, 11, 0.12);
    border: 1px solid rgba(245, 158, 11, 0.3);
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 14px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}

h2.panel-title {{
    font-size: 48px;
    font-weight: 900;
    line-height: 1.15;
    color: #ffffff;
}}

.breakdown-box {{
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 20px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 18px;
}}

.breakdown-item {{
    display: flex;
    gap: 16px;
}}

.breakdown-num {{
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: #005c4b;
    color: #34d399;
    font-weight: 800;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}}

.breakdown-item h4 {{
    font-size: 17px;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 4px;
}}

.breakdown-item p {{
    font-size: 14px;
    color: #94a3b8;
    line-height: 1.5;
}}

.kpi-row {{
    display: flex;
    gap: 20px;
}}

.kpi-card {{
    flex: 1;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 20px;
    text-align: center;
}}

.kpi-value {{
    font-size: 36px;
    font-weight: 900;
    color: #10b981;
    margin-bottom: 4px;
}}

.kpi-label {{
    font-size: 13px;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
</style>
</head>
<body>
<div class="ambient-glow"></div>
<div class="ambient-glow-2"></div>

<div class="container">
    <!-- Phone Output -->
    <div class="phone-frame wide">
        <div class="dynamic-island"></div>
        <div class="phone-status-bar">
            <span>09:44</span>
            <span>5G 􀛨 100%</span>
        </div>

        <div class="wa-header">
            <div class="wa-avatar-box">
                <div class="wa-avatar">🤖</div>
                <div class="verified-badge">✓</div>
            </div>
            <div class="wa-user-info">
                <div class="wa-user-name">CopyBot AI <span style="color:#10b981;font-size:13px;">✔</span></div>
                <div class="wa-status">online</div>
            </div>
        </div>

        <div class="wa-chat-area">
            <div class="wa-bubble incoming" style="background:#182229; border-left: 4px solid #10b981;">
                🔥 <strong>Your high-converting STORIES sequence is ready!</strong><br><br>
                <strong>SCREEN 1 | HOOK (Pattern Interrupt)</strong><br>
                <em>🎥 Plain background text or focused direct-to-camera video:</em><br>
                The worst feeling in fitness isn't failing.<br>
                <strong>It's living in the 'almost'.</strong><br><br>
                Training 6 days a week, giving up weekends on diet, looking in the mirror and still just looking like someone who "tries" — with zero real muscle definition.
                <div class="wa-bubble-meta">09:44</div>
            </div>

            <div class="wa-bubble incoming" style="background:#182229; border-left: 4px solid #38bdf8;">
                <strong>SCREEN 3 | INVISIBLE MECHANISM (Technical Authority)</strong><br>
                <em>🎥 Simple graphic element or training schedule print:</em><br>
                Dense muscle doesn't respond to <strong>exhaustion</strong>. It responds to <strong>mechanical tension</strong>.<br><br>
                Training 6 consecutive days accumulating metabolic fatigue elevates cortisol and blunts high-threshold motor unit recruitment.
                <div class="wa-bubble-meta">09:44</div>
            </div>

            <div class="wa-bubble incoming" style="background:#182229; border-left: 4px solid #f59e0b;">
                <strong>SCREEN 6 | DIRECT OFFER & CTA</strong><br>
                I am opening <strong>4 spots</strong> today for my High Performance Coaching this month.<br><br>
                👉 Reply <strong>"RESULTS"</strong> to receive the private selection criteria.
                <div class="wa-bubble-meta">09:45</div>
            </div>
        </div>

        <div class="wa-input-bar">
            <div class="wa-input-pill">Type 'MENU' or request changes...</div>
            <div class="wa-mic-btn">➤</div>
        </div>
    </div>

    <!-- Right Side Breakdown -->
    <div class="right-panel">
        <div class="section-tag">Automated Content Delivery</div>
        
        <h2 class="panel-title">
            Persuasive High-Converting Copy Generated in Seconds
        </h2>
        
        <div class="breakdown-box">
            <div class="breakdown-item">
                <div class="breakdown-num">1</div>
                <div>
                    <h4>Pattern Interrupt Hook</h4>
                    <p>Captures 100% of user attention within the first 3 seconds without clickbait, reframing common market frustrations.</p>
                </div>
            </div>

            <div class="breakdown-item">
                <div class="breakdown-num">2</div>
                <div>
                    <h4>The Invisible Mechanism (Scientific Proof)</h4>
                    <p>Substitutes superficial tips with technical authority, establishing undeniable credibility and intellectual trust.</p>
                </div>
            </div>

            <div class="breakdown-item">
                <div class="breakdown-num">3</div>
                <div>
                    <h4>Director's Scene & Camera Notes</h4>
                    <p>Provides exact production instructions (camera angles, typography, tone of voice) for creators who record video or post stories.</p>
                </div>
            </div>

            <div class="breakdown-item">
                <div class="breakdown-num">4</div>
                <div>
                    <h4>Frictionless Direct Call-To-Action</h4>
                    <p>Engineered for high reply rates on Instagram Stories and direct WhatsApp pipeline generation.</p>
                </div>
            </div>
        </div>

        <div class="kpi-row">
            <div class="kpi-card">
                <div class="kpi-value">&lt; 2.5s</div>
                <div class="kpi-label">Generation Latency</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">Gemini 3.8</div>
                <div class="kpi-label">Flash Model API</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">100%</div>
                <div class="kpi-label">State Persistence</div>
            </div>
        </div>
    </div>
</div>
</body>
</html>
"""

SLIDE_4_HTML = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
{SHARED_STYLES}

.container {{
    width: 1720px;
    height: 940px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    z-index: 2;
}}

.info-content {{
    flex: 1;
    max-width: 940px;
    display: flex;
    flex-direction: column;
    gap: 24px;
}}

.section-tag {{
    align-self: flex-start;
    display: flex;
    align-items: center;
    gap: 8px;
    color: #a855f7;
    background: rgba(168, 85, 247, 0.12);
    border: 1px solid rgba(168, 85, 247, 0.35);
    padding: 6px 18px;
    border-radius: 999px;
    font-size: 14px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}

h2.main-title {{
    font-size: 52px;
    font-weight: 900;
    line-height: 1.1;
    color: #ffffff;
}}

h2.main-title span {{
    color: #c084fc;
}}

p.subtitle {{
    font-size: 19px;
    color: #94a3b8;
    line-height: 1.5;
}}

.feature-list {{
    display: flex;
    flex-direction: column;
    gap: 14px;
}}

.feature-row {{
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 16px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
}}

.feature-check {{
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: rgba(168, 85, 247, 0.2);
    border: 1px solid #a855f7;
    color: #c084fc;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    flex-shrink: 0;
}}

.feature-row-text h4 {{
    font-size: 16px;
    color: #f1f5f9;
    font-weight: 700;
    margin-bottom: 2px;
}}

.feature-row-text p {{
    font-size: 13.5px;
    color: #94a3b8;
}}

.phone-frame.wide {{
    width: 500px;
    height: 920px;
    border-radius: 54px;
}}
</style>
</head>
<body>
<div class="ambient-glow"></div>
<div class="ambient-glow-2"></div>

<div class="container">
    <div class="info-content">
        <div class="section-tag">B2B Sales & Objection Handling</div>
        
        <h2 class="main-title">
            Consultative <span>Objection Reframing</span> for WhatsApp Lead Conversion
        </h2>
        
        <p class="subtitle">
            Turn hesitant leads into closed deals with sophisticated cognitive reframing instead of pushy salesperson tactics.
        </p>

        <div class="feature-list">
            <div class="feature-row">
                <div class="feature-check">✓</div>
                <div class="feature-row-text">
                    <h4>Reframe the 'No Time' Objection</h4>
                    <p>Transforms lack of time from an excuse to delay into the primary symptom of missing processes.</p>
                </div>
            </div>

            <div class="feature-row">
                <div class="feature-check">✓</div>
                <div class="feature-row-text">
                    <h4>Drastic Cognitive Friction Reduction</h4>
                    <p>Highlights micro-commitments (only 90 minutes in Week 1) to remove fear of operational drag.</p>
                </div>
            </div>

            <div class="feature-row">
                <div class="feature-check">✓</div>
                <div class="feature-row-text">
                    <h4>Instant Copy-Paste Readiness</h4>
                    <p>Clean formatting with WhatsApp bolding (*text*) and italics (_text_) ready for direct outreach.</p>
                </div>
            </div>

            <div class="feature-row">
                <div class="feature-check">✓</div>
                <div class="feature-row-text">
                    <h4>Multi-Turn Adjustments</h4>
                    <p>Users can reply with "Make it shorter" or "Tone down the urgency" for instant refinement.</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Phone View with Objection Reframing -->
    <div class="phone-frame wide">
        <div class="dynamic-island"></div>
        <div class="phone-status-bar">
            <span>10:15</span>
            <span>5G 􀛨 100%</span>
        </div>

        <div class="wa-header">
            <div class="wa-avatar-box">
                <div class="wa-avatar">🤖</div>
                <div class="verified-badge">✓</div>
            </div>
            <div class="wa-user-info">
                <div class="wa-user-name">CopyBot AI <span style="color:#10b981;font-size:13px;">✔</span></div>
                <div class="wa-status">online</div>
            </div>
        </div>

        <div class="wa-chat-area">
            <div class="wa-bubble outgoing">
                Create a closing message for a lead who said: "I don't have time to implement the consulting right now".
                <div class="wa-bubble-meta">10:14 <span class="wa-checkmarks">✓✓</span></div>
            </div>

            <div class="wa-bubble incoming" style="background:#182229; border-left: 4px solid #a855f7;">
                🔥 <strong>B2B Consultative Closing Script Ready:</strong><br><br>
                Hi, Carlos! Hope you're having a productive week.<br><br>
                Reflecting on our chat yesterday and your note about <em>"being short on time to implement right now"</em>, I'd love to share a quick perspective:<br><br>
                Lack of time in your daily routine today is <strong>not the reason to postpone</strong> restructuring — it is the <strong>direct symptom</strong> of an operation that remains centralized in you.<br><br>
                You're spending 20 to 25 hours every week putting out operational fires your team should handle autonomously.<br><br>
                In Phase 1, the time required from you is <strong>just 90 minutes in the first week</strong>. All remaining operational workflow is executed by my team.<br><br>
                <em>You don't need free time to organize the business. You need an organized business to finally have free time.</em><br><br>
                Does it make sense to talk for 15 minutes this Thursday at 10 AM or 2 PM?
                <div class="wa-bubble-meta">10:15</div>
            </div>
        </div>

        <div class="wa-input-bar">
            <div class="wa-input-pill">Type 'MENU' or request changes...</div>
            <div class="wa-mic-btn">➤</div>
        </div>
    </div>
</div>
</body>
</html>
"""

def generate_screenshots():
    slides = [
        ("fiverr_1_cover_showcase.html", SLIDE_1_HTML, "fiverr_1_cover_showcase.png"),
        ("fiverr_2_interactive_onboarding.html", SLIDE_2_HTML, "fiverr_2_interactive_onboarding.png"),
        ("fiverr_3_neurocopy_delivery.html", SLIDE_3_HTML, "fiverr_3_neurocopy_delivery.png"),
        ("fiverr_4_whatsapp_lead_pitch.html", SLIDE_4_HTML, "fiverr_4_whatsapp_lead_pitch.png"),
    ]

    print("Iniciando geração de screenshots em inglês com Playwright (canal Edge)...")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        # 1920x1080 with device_scale_factor=2 produces ultra-crisp 3840x2160 images
        page = browser.new_page(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2
        )

        for html_filename, html_content, png_filename in slides:
            temp_html_path = PORTFOLIO_DIR / html_filename
            output_png_path = PORTFOLIO_DIR / png_filename

            temp_html_path.write_text(html_content, encoding="utf-8")
            print(f"Renderizando {png_filename}...")
            
            page.goto(temp_html_path.as_uri())
            page.wait_for_timeout(500) # Ensure rendering is completely settled
            page.screenshot(path=str(output_png_path))
            print(f"[OK] Salvo com sucesso: {output_png_path.name}")

        browser.close()

    print("\nTodas as 4 imagens do portfólio foram regeradas em inglês em:")
    print(str(PORTFOLIO_DIR))

if __name__ == "__main__":
    generate_screenshots()
