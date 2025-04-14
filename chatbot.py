import dearpygui.dearpygui as dpg
import os
import requests
import base64
import json
import threading
import time
from datetime import datetime
from PIL import ImageGrab
import io

# Initialize DearPyGui
dpg.create_context()

# Application state
class AppState:
    def __init__(self):
        self.api_key = self.load_api_key()
        self.api_key_saved = bool(self.api_key)
        self.is_typing = False
        self.messages = []
        self.status = "Ready"
    
    def load_api_key(self):
        # Try from environment
        api_key = os.environ.get("GEMINI_API_KEY", "")
        
        # If not there, try from file
        if not api_key and os.path.exists("api_key.txt"):
            try:
                with open("api_key.txt", "r") as f:
                    api_key = f.read().strip()
            except:
                pass
        
        return api_key
    
    def save_api_key(self, api_key):
        self.api_key = api_key
        try:
            with open("api_key.txt", "w") as f:
                f.write(api_key)
            self.api_key_saved = True
            return True
        except:
            return False

# Create app state
app_state = AppState()

# Create message handler for chat
class MessageHandler:
    def __init__(self, state):
        self.state = state
        self.message_count = 0
        
    def add_message(self, content, sender):
        timestamp = datetime.now().strftime("%H:%M:%S")
        message_id = f"message_{self.message_count}"
        self.message_count += 1
        
        # Add to state
        self.state.messages.append({
            "id": message_id,
            "content": content,
            "sender": sender,
            "timestamp": timestamp
        })
        
        # Update UI
        self.update_chat_ui()
    
    def update_chat_ui(self):
        # Clear chat window
        dpg.delete_item("chat_window", children_only=True)
        
        # Add messages
        for msg in self.state.messages:
            with dpg.group(parent="chat_window"):
                # Calculate width based on parent window
                window_width = dpg.get_item_width("chat_window")
                message_width = min(int(window_width * 0.7), 500)  # 70% of window width, max 500px
                
                # Format timestamp
                time_text = f"[{msg['timestamp']}]"
                
                if msg["sender"] == "user":
                    # User message (right-aligned)
                    with dpg.group(horizontal=True):
                        # Add space to push message to right
                        dpg.add_spacer(width=window_width - message_width - 20)
                        
                        # Message container
                        with dpg.child_window(width=message_width, height=0, no_scrollbar=True, 
                                            tag=f"{msg['id']}_container"):
                            # Style user message
                            dpg.bind_item_theme(f"{msg['id']}_container", user_message_theme)
                            
                            # Add timestamp (right-aligned)
                            with dpg.group(horizontal=True):
                                dpg.add_spacer(width=message_width - 100)
                                dpg.add_text(time_text, color=[150, 150, 150])
                            
                            # Add sender and message
                            dpg.add_text("You")
                            dpg.add_text(msg["content"], wrap=message_width - 20)
                else:
                    # Bot message (left-aligned)
                    with dpg.group(horizontal=True):
                        # Avatar placeholder
                        with dpg.drawlist(width=40, height=40):
                            # Draw a shield shape for the avatar
                            dpg.draw_circle([20, 20], 18, color=[0, 120, 255, 255], fill=[30, 30, 50, 255])
                            # Draw shield logo
                            dpg.draw_polygon([[20, 10], [30, 15], [25, 30], [20, 35], [15, 30], [10, 15]], 
                                             color=[0, 180, 255, 255], fill=[0, 140, 220, 255])
                            # Draw lock
                            dpg.draw_circle([20, 22], 5, color=[220, 220, 220, 255], fill=[220, 220, 220, 255])
                            dpg.draw_line([20, 22], [20, 28], color=[220, 220, 220, 255], thickness=2)
                        
                        # Message container
                        with dpg.child_window(width=message_width, height=0, no_scrollbar=True, 
                                            tag=f"{msg['id']}_container"):
                            # Style bot message
                            dpg.bind_item_theme(f"{msg['id']}_container", bot_message_theme)
                            
                            # Add timestamp and sender
                            dpg.add_text(f"{time_text} Cybersecurity Advisor", color=[150, 150, 150])
                            
                            # Add message
                            dpg.add_text(msg["content"], wrap=message_width - 20)
        
        # Scroll to bottom
        dpg.set_y_scroll("chat_window", -1.0)

# Create message handler
message_handler = MessageHandler(app_state)

# API Functions
def query_gemini(message, api_key):
    """Send a query to the Gemini API and return the response"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"""You are a cybersecurity expert advisor, specializing in explaining complex security concepts in simple terms that anyone can understand.

You use friendly, conversational language while still being informative and educational.

Format your responses in a clean, readable way:
1. Use clear paragraphs instead of markdown-style formatting
2. Don't use ** for bold text or # for headers
3. Use plain language and avoid technical jargon unless necessary
4. When listing points, use proper bullet points or numbers
5. Break up long text with proper spacing

Please respond to the following query about cybersecurity: {message}"""
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024
        }
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
    
    response_data = response.json()
    
    try:
        text_response = response_data["candidates"][0]["content"]["parts"][0]["text"]
        return text_response
    except (KeyError, IndexError) as e:
        raise Exception(f"Failed to parse API response: {str(e)}")

def analyze_screenshot(image_base64, api_key):
    """Analyze a screenshot using Gemini Vision API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": """As a cybersecurity expert, analyze this screenshot for potential security threats, suspicious elements, or phishing attempts.

Look for elements like:
• Suspicious URLs
• Fake login forms
• Misleading buttons
• Strange emails
• Security warnings
• Anything that could be a security risk

Explain your findings in simple terms that a non-technical person would understand. If you find anything suspicious, explain why it's concerning and what the user should do. If it looks safe, just say so briefly."""
                    },
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": image_base64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024
        }
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
    
    response_data = response.json()
    
    try:
        text_response = response_data["candidates"][0]["content"]["parts"][0]["text"]
        return text_response
    except (KeyError, IndexError) as e:
        raise Exception(f"Failed to parse API response: {str(e)}")

# UI Callbacks
def send_message_callback():
    message = dpg.get_value("message_input")
    if not message.strip():
        return
    
    # Clear input
    dpg.set_value("message_input", "")
    
    # Add user message to chat
    message_handler.add_message(message, "user")
    
    # If API key not set, show message
    if not app_state.api_key_saved:
        message_handler.add_message("Please set your Gemini API key in the settings panel first", "bot")
        show_settings_panel()
        return
    
    # Update status
    app_state.status = "Processing..."
    dpg.set_value("status_text", app_state.status)
    
    # Start typing indicator
    start_typing_animation()
    
    # Process message in background
    threading.Thread(target=process_message, args=(message,)).start()

def process_message(message):
    try:
        # Get response from API
        response = query_gemini(message, app_state.api_key)
        
        # Stop typing animation
        stop_typing_animation()
        
        # Add bot message
        dpg.set_value("status_text", "Adding response...")
        dpg.configure_item("send_button", enabled=False)
        
        # Add to UI (from main thread)
        add_bot_message_with_delay(response)
        
    except Exception as e:
        # Stop typing animation
        stop_typing_animation()
        
        # Add error message
        error_message = f"Error: {str(e)}"
        dpg.configure_item("send_button", enabled=True)
        message_handler.add_message(error_message, "bot")
        
        # Update status
        app_state.status = "Error"
        dpg.set_value("status_text", app_state.status)

def add_bot_message_with_delay(message):
    # Reset status
    app_state.status = "Ready"
    dpg.set_value("status_text", app_state.status)
    
    # Add the message
    message_handler.add_message(message, "bot")
    
    # Re-enable send button
    dpg.configure_item("send_button", enabled=True)

def start_typing_animation():
    app_state.is_typing = True
    typing_frame = dpg.add_child_window(parent="chat_window", autosize_x=True, height=50, tag="typing_indicator")
    dpg.bind_item_theme(typing_frame, bot_message_theme)
    
    with dpg.group(parent=typing_frame, horizontal=True):
        dpg.add_text("Typing")
        dpg.add_text(".", tag="typing_dot1")
        dpg.add_text(".", tag="typing_dot2")
        dpg.add_text(".", tag="typing_dot3")
    
    # Start animation
    animate_typing_dots()
    
    # Scroll to bottom
    dpg.set_y_scroll("chat_window", -1.0)

def animate_typing_dots():
    if not app_state.is_typing:
        return
    
    # Check if typing indicator exists
    if not dpg.does_item_exist("typing_indicator"):
        return
    
    # Define dot states (visible or not)
    current_time = time.time()
    dot1 = (current_time % 1.0) > 0.25
    dot2 = (current_time % 1.0) > 0.5
    dot3 = (current_time % 1.0) > 0.75
    
    # Update dots visibility
    if dpg.does_item_exist("typing_dot1"):
        dpg.configure_item("typing_dot1", show=dot1)
    if dpg.does_item_exist("typing_dot2"):
        dpg.configure_item("typing_dot2", show=dot2)
    if dpg.does_item_exist("typing_dot3"):
        dpg.configure_item("typing_dot3", show=dot3)
    
    # Schedule next animation frame
    dpg.set_frame_callback(0, animate_typing_dots)

def stop_typing_animation():
    app_state.is_typing = False
    
    # Remove typing indicator
    if dpg.does_item_exist("typing_indicator"):
        dpg.delete_item("typing_indicator")

def save_api_key_callback():
    new_key = dpg.get_value("api_key_input")
    if not new_key.strip():
        # Show error
        dpg.set_value("api_status", "Error: API key cannot be empty")
        dpg.configure_item("api_status", color=[255, 100, 100])
        return
    
    # Save key
    if app_state.save_api_key(new_key):
        # Test connection
        test_api_connection(new_key)
    else:
        # Show error
        dpg.set_value("api_status", "Error: Could not save API key")
        dpg.configure_item("api_status", color=[255, 100, 100])

def test_api_connection(api_key):
    # Update status
    dpg.set_value("api_status", "Testing connection...")
    dpg.configure_item("api_status", color=[150, 150, 255])
    
    def test_connection_thread():
        try:
            # Try a simple query
            query_gemini("Test connection", api_key)
            
            # Update status on success
            dpg.set_value("api_status", "Connection successful!")
            dpg.configure_item("api_status", color=[100, 255, 100])
            
            # Add message to chat
            message_handler.add_message("API connection verified. You can now chat with me about cybersecurity topics!", "bot")
            
            # Close settings panel after a delay
            time.sleep(1)
            dpg.configure_item("settings_window", show=False)
            
        except Exception as e:
            # Update status on error
            error_msg = f"Connection failed: {str(e)}"
            dpg.set_value("api_status", error_msg)
            dpg.configure_item("api_status", color=[255, 100, 100])
    
    # Start test in background
    threading.Thread(target=test_connection_thread).start()

def show_settings_panel():
    if not dpg.is_item_shown("settings_window"):
        dpg.configure_item("settings_window", show=True)
        dpg.set_value("api_key_input", app_state.api_key)

def hide_settings_panel():
    dpg.configure_item("settings_window", show=False)

def scan_screen_callback():
    # Check if API key is set
    if not app_state.api_key_saved:
        message_handler.add_message("Please set your Gemini API key in the settings panel first", "bot")
        show_settings_panel()
        return
    
    # Inform user
    message_handler.add_message("Taking screenshot of your screen for security analysis...", "bot")
    
    # Update status
    app_state.status = "Taking screenshot..."
    dpg.set_value("status_text", app_state.status)
    
    # Start in background
    threading.Thread(target=capture_screen).start()

def capture_screen():
    try:
        # Minimize viewport briefly to avoid capturing it
        dpg.minimize_viewport()
        time.sleep(0.5)
        
        # Take screenshot
        screenshot = ImageGrab.grab()
        
        # Restore viewport
        dpg.maximize_viewport()
        
        # Convert to base64
        buffered = io.BytesIO()
        screenshot.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        # Update status
        app_state.status = "Analyzing screenshot..."
        dpg.set_value("status_text", app_state.status)
        
        # Start typing animation
        start_typing_animation()
        
        # Process the screenshot
        process_screenshot(img_str)
        
    except Exception as e:
        # Restore viewport in case of error
        dpg.maximize_viewport()
        
        # Add error message
        error_message = f"Error taking screenshot: {str(e)}"
        message_handler.add_message(error_message, "bot")
        
        # Update status
        app_state.status = "Error"
        dpg.set_value("status_text", app_state.status)
        
        # Stop typing animation
        stop_typing_animation()

def process_screenshot(img_str):
    try:
        # Analyze screenshot
        response = analyze_screenshot(img_str, app_state.api_key)
        
        # Stop typing animation
        stop_typing_animation()
        
        # Check if response contains threat indicators
        threat_keywords = ['threat', 'suspicious', 'malicious', 'phishing', 'scam', 'unsafe', 'risk', 
                         'malware', 'dangerous', 'warning', 'vulnerability', 'hack']
        
        is_threat = any(keyword in response.lower() for keyword in threat_keywords)
        
        # Format response
        if is_threat:
            prefix = "⚠️ SECURITY ALERT: "
            show_notification("Security Alert", "Potential security issues detected", [255, 100, 100])
        else:
            prefix = "✅ SCREEN SCAN: "
            show_notification("Scan Complete", "No immediate security threats detected", [100, 255, 100])
        
        message = f"{prefix}{response}"
        
        # Add to chat
        message_handler.add_message(message, "bot")
        
        # Update status
        app_state.status = "Ready"
        dpg.set_value("status_text", app_state.status)
        
    except Exception as e:
        # Stop typing animation
        stop_typing_animation()
        
        # Add error message
        error_message = f"Error analyzing screenshot: {str(e)}"
        message_handler.add_message(error_message, "bot")
        
        # Update status
        app_state.status = "Error"
        dpg.set_value("status_text", app_state.status)

def show_notification(title, message, color):
    # Delete previous notification if exists
    if dpg.does_item_exist("notification_window"):
        dpg.delete_item("notification_window")
    
    # Calculate position (centered at top)
    viewport_width = dpg.get_viewport_width()
    
    # Create notification
    with dpg.window(label=title, width=300, height=100, pos=[viewport_width/2 - 150, 30],
                   no_collapse=True, no_close=True, tag="notification_window"):
        dpg.add_text(message)
        dpg.add_button(label="OK", callback=lambda: dpg.delete_item("notification_window"),
                      width=-1)
    
    # Set notification color
    with dpg.theme() as notification_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, color)
    
    dpg.bind_item_theme("notification_window", notification_theme)
    
    # Auto-close after 5 seconds
    dpg.set_frame_callback(5000, lambda: dpg.does_item_exist("notification_window") and dpg.delete_item("notification_window"))

def on_key_press(sender, key_data):
    # Check if Enter was pressed in message input
    if key_data == 257:  # Enter key
        if dpg.is_item_focused("message_input"):
            send_message_callback()

# Create viewport and setup
dpg.create_viewport(title="Cybersecurity Advisor", width=900, height=700, min_width=700, min_height=500)
dpg.set_viewport_resize_callback(lambda: message_handler.update_chat_ui())

# Set up dear PyGui
dpg.setup_dearpygui()

# Create themes
with dpg.theme() as global_theme:
    with dpg.theme_component(dpg.mvAll):
        # Background colors
        dpg.add_theme_color(dpg.mvThemeCol_WindowBg, [15, 15, 20])
        dpg.add_theme_color(dpg.mvThemeCol_TitleBg, [30, 30, 50])
        dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, [40, 40, 80])
        
        # Text colors
        dpg.add_theme_color(dpg.mvThemeCol_Text, [220, 220, 220])
        
        # Button colors
        dpg.add_theme_color(dpg.mvThemeCol_Button, [40, 80, 150])
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [60, 100, 180])
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, [80, 120, 200])
        
        # Input field colors
        dpg.add_theme_color(dpg.mvThemeCol_FrameBg, [25, 25, 35])
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, [35, 35, 45])
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, [45, 45, 65])
        
        # Scrollbar colors
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, [15, 15, 20])
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, [40, 40, 60])
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, [50, 50, 70])
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, [60, 60, 80])
        
        # Rounded corners
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5)
        dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 5)
        dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 5)
        dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 6, 4)

# Message themes
with dpg.theme() as user_message_theme:
    with dpg.theme_component(dpg.mvAll):
        dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [30, 70, 120])
        dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 10)

with dpg.theme() as bot_message_theme:
    with dpg.theme_component(dpg.mvAll):
        dpg.add_theme_color(dpg.mvThemeCol_ChildBg, [35, 35, 50])
        dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 10)

# Main Chat window
with dpg.window(label="Cybersecurity Advisor", tag="main_window"):
    # Top menu bar
    with dpg.menu_bar():
        with dpg.menu(label="Settings"):
            dpg.add_menu_item(label="API Key Settings", callback=show_settings_panel)
        
        with dpg.menu(label="Help"):
            dpg.add_menu_item(label="About")
    
    # Main layout with splitter
    with dpg.group(horizontal=True):
        # Chat area
        with dpg.child_window(width=-250, height=-100, tag="chat_container"):
            # Create scrollable chat window
            with dpg.child_window(autosize_x=True, height=-5, tag="chat_window"):
                # Messages will be added here dynamically
                pass
        
        # Info sidebar
        with dpg.child_window(width=250, height=-100, tag="sidebar"):
            dpg.add_text("Cybersecurity Assistant", color=[100, 180, 255])
            dpg.add_separator()
            dpg.add_spacer(height=5)
            
            # Shield icon
            with dpg.drawlist(width=100, height=100):
                dpg.draw_circle([50, 50], 40, color=[0, 120, 255, 255], fill=[30, 30, 50, 255])
                dpg.draw_polygon([[50, 20], [80, 30], [70, 80], [50, 90], [30, 80], [20, 30]], 
                                 color=[0, 180, 255, 255], fill=[0, 140, 220, 255])
                dpg.draw_circle([50, 50], 15, color=[220, 220, 220, 255], fill=[220, 220, 220, 255])
                dpg.draw_line([50, 50], [50, 70], color=[220, 220, 220, 255], thickness=5)
            
            dpg.add_spacer(height=10)
            dpg.add_separator()
            dpg.add_spacer(height=10)
            
            # Quick actions
            dpg.add_text("Quick Actions:")
            dpg.add_button(label="Scan Screen for Threats", callback=scan_screen_callback, width=-1)
            dpg.add_button(label="Clear Chat", callback=lambda: dpg.delete_item("chat_window", children_only=True), width=-1)
            
            dpg.add_spacer(height=10)
            dpg.add_separator()
            dpg.add_spacer(height=10)
            
            # Suggested topics
            dpg.add_text("Suggested Topics:")
            topics = [
                "What is phishing?",
                "How to create secure passwords",
                "Explain two-factor authentication",
                "What is ransomware?"
            ]
            
            for topic in topics:
                dpg.add_button(
                    label=topic, 
                    callback=lambda s, a, u: [
                        dpg.set_value("message_input", u),
                        send_message_callback()
                    ],
                    user_data=topic,
                    width=-1
                )
    
    # Input area
    with dpg.group(horizontal=True, tag="input_area"):
        # Chat input
        dpg.add_input_text(tag="message_input", width=-100, height=40, hint="Type your message here...")
        
        # Send button
        dpg.add_button(label="Send", callback=send_message_callback, width=80, height=25, tag="send_button")
    
    # Status bar
    with dpg.group(horizontal=True):
        dpg.add_text("Status: ", color=[150, 150, 150])
        dpg.add_text("Ready", color=[100, 255, 100], tag="status_text")

# Settings window (hidden by default)
with dpg.window(label="API Key Settings", width=400, height=200, pos=[250, 200], 
               show=False, tag="settings_window", modal=True):
    dpg.add_text("Enter your Gemini API Key:")
    dpg.add_input_text(tag="api_key_input", width=-1, password=True, hint="Paste your API key here")
    
    dpg.add_spacer(height=5)
    dpg.add_text("Your key is stored locally and never shared")
    
    dpg.add_spacer(height=20)
    with dpg.group(horizontal=True):
        dpg.add_button(label="Save & Test", callback=save_api_key_callback, width=150)
        dpg.add_button(label="Cancel", callback=hide_settings_panel, width=150)
    
    dpg.add_spacer(height=10)
    dpg.add_text("", tag="api_status")

# Key handler
with dpg.handler_registry():
    dpg.add_key_release_handler(callback=on_key_press)

# Apply theme
dpg.bind_theme(global_theme)

# Welcome message
message_handler.add_message("Welcome! I'm your Cybersecurity Advisor. I can help you understand online threats, secure your digital life, and protect yourself from scams and malware. What would you like to know about cybersecurity today?", "bot")

# Show viewport and start
dpg.show_viewport()
dpg.set_primary_window("main_window", True)
dpg.start_dearpygui()
dpg.destroy_context()