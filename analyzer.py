import re
from datetime import datetime
from collections import Counter
import emoji
from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Simplified Hinglish dictionary
HINGLISH_POSITIVE = {"accha", "khush", "pyaar", "dil", "awesome"}
HINGLISH_NEGATIVE = {"gussa", "dukhi", "sorry", "nafrat", "problem"}

async def parse_chat(chat_data, your_name, other_name):
    if not chat_data or not your_name or not other_name:
        raise ValueError("Chat data or names are missing.")

    lines = chat_data.splitlines()
    messages = []
    
    # Remove sampling to process all messages
    # If performance becomes an issue, we can reintroduce sampling with a better strategy
    pattern = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),?\s*(\d{1,2}:\d{2}(:\d{2})?)\s*(am|pm)?\s*[-–]\s*([^:]+):\s*(.*)", re.IGNORECASE)
    timestamp_formats = [
        "%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p", "%d/%m/%Y %I:%M %p",
        "%m/%d/%y %I:%M %p", "%d/%m/%y %I:%M %p",
        "%m/%d/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M", "%d/%m/%Y %H:%M",
        "%m/%d/%y %H:%M", "%d/%m/%y %H:%M"
    ]

    for line in lines:
        line = line.strip()
        if not line or "encrypted" in line.lower() or "<media" in line.lower():
            continue
        
        match = pattern.match(line)
        if match:
            date_str, time_str, *extra, sender, content = match.groups()
            sender_mapped = "You" if your_name.lower() in sender.lower() else "Her"
            timestamp_str = f"{date_str} {time_str}"
            if extra and extra[0]:
                timestamp_str += f" {extra[0]}"
            
            timestamp = None
            for fmt in timestamp_formats:
                try:
                    timestamp = datetime.strptime(timestamp_str, fmt)
                    break
                except ValueError:
                    continue
            
            if timestamp and content:
                messages.append({"timestamp": timestamp, "sender": sender_mapped, "content": content})
            else:
                # Skip messages with invalid timestamps or empty content
                continue
        else:
            # Skip lines that don't match the pattern
            continue

    if not messages:
        raise ValueError(f"No valid chat messages found for '{your_name}' or '{other_name}'.")
    
    return messages

async def analyze_conversation(messages):
    you_msgs = [m for m in messages if m["sender"] == "You"]
    her_msgs = [m for m in messages if m["sender"] == "Her"]
    total_count = len(messages)

    # Conversation Flow
    flow = Counter(m["timestamp"].hour for m in messages)
    flow_dict = {str(h): flow.get(h, 0) for h in range(24)}

    # Engagement Metrics
    you_interest = (len(you_msgs) / total_count * 100) if total_count > 0 else 0
    her_interest = (len(her_msgs) / total_count * 100) if total_count > 0 else 0

    initiations = {"You": 0, "Her": 0}
    initiations[messages[0]["sender"]] += 1
    for i in range(1, len(messages)):
        if (messages[i]["timestamp"] - messages[i-1]["timestamp"]).total_seconds() / 60 > 30:
            initiations[messages[i]["sender"]] += 1
    total_initiations = sum(initiations.values())
    you_init = (initiations["You"] / total_initiations * 100) if total_initiations > 0 else 0
    her_init = (initiations["Her"] / total_initiations * 100) if total_initiations > 0 else 0

    # Emoji Analysis
    def get_emojis(msgs):
        all_emojis = [c for m in msgs for c in m["content"] if c in emoji.EMOJI_DATA]
        return [e[0] for e in Counter(all_emojis).most_common(3)] or ["None"]
    you_emojis = get_emojis(you_msgs)
    her_emojis = get_emojis(her_msgs)

    # Top Words Analysis
    stop_words = {"i", "you", "the", "a", "and", "to", "is", "it", "in", "on"}
    def get_words(msgs):
        all_words = [w.lower() for m in msgs for w in re.findall(r'\w+', m["content"]) if w.lower() not in stop_words]
        return [w[0] for w in Counter(all_words).most_common(3)] or ["None"]
    you_words = get_words(you_msgs)
    her_words = get_words(her_msgs)

    # Sentiment Analysis
    pos_words = {"good", "great", "happy", "nice", "cool", "love", "awesome", "fun", "sweet", "amazing"} | HINGLISH_POSITIVE
    neg_words = {"bad", "sad", "sorry", "hate", "boring", "annoying", "ugh", "stupid"} | HINGLISH_NEGATIVE
    def get_sentiment(msgs):
        pos = sum(1 for m in msgs for w in re.findall(r'\w+', m["content"].lower()) if w in pos_words)
        neg = sum(1 for m in msgs for w in re.findall(r'\w+', m["content"].lower()) if w in neg_words)
        total = pos + neg
        return {"POSITIVE": pos / total * 100 if total > 0 else 50, "NEGATIVE": neg / total * 100 if total > 0 else 50}
    you_sentiment = get_sentiment(you_msgs)
    her_sentiment = get_sentiment(her_msgs)

    # Response Time Analysis
    def get_response_time(msgs, other_msgs):
        times = []
        sorted_msgs = sorted(msgs, key=lambda x: x["timestamp"])
        sorted_other_msgs = sorted(other_msgs, key=lambda x: x["timestamp"])
        
        for i, curr in enumerate(sorted_msgs):
            last_other = None
            for other in sorted_other_msgs:
                if other["timestamp"] < curr["timestamp"]:
                    last_other = other
                else:
                    break
            if last_other:
                time_diff = (curr["timestamp"] - last_other["timestamp"]).total_seconds() / 60
                if time_diff > 0 and time_diff < 1440:  # Ignore responses > 24 hours
                    times.append(time_diff)
        
        return sum(times) / len(times) if times else float('inf')

    you_response = get_response_time(you_msgs, her_msgs)
    her_response = get_response_time(her_msgs, you_msgs)

    # Refined Love Meter Calculation
    sentiment_score = ((you_sentiment["POSITIVE"] + her_sentiment["POSITIVE"]) / 2) * 0.3  # 30%
    emoji_score = (len(set(you_emojis) & set(her_emojis)) / 3 * 20)  # 20%
    response_score = 0
    if you_response != float('inf') and her_response != float('inf'):
        avg_response = (you_response + her_response) / 2
        response_score = (min(60, max(0, 60 - avg_response)) / 60 * 20)  # 20%
    else:
        response_score = 10
    engagement_balance = (1 - abs(you_interest - her_interest) / 100) * 20  # 20%
    emotional_words = {"love", "pyaar", "miss", "care", "sorry", "dil"}
    emotional_count = sum(1 for m in messages for w in re.findall(r'\w+', m["content"].lower()) if w in emotional_words)
    emotional_score = min(emotional_count / 10, 1) * 10  # 10%

    love_meter = sentiment_score + emoji_score + response_score + engagement_balance + emotional_score
    love_meter = min(100, max(0, int(love_meter)))

    # Conversation Highlights
    first_message = messages[0] if messages else None
    longest_message = max(messages, key=lambda m: len(m["content"]) if m["content"] else 0, default=None)

    # Flags and Insights
    red_flags = []
    green_flags = []
    similarities = []
    differences = []

    if you_response == float('inf'):
        red_flags.append("No response time data for You (not enough messages)")
    elif you_response > 60:
        red_flags.append(f"Slow replies from You ({you_response:.1f} min)")
    if her_response == float('inf'):
        red_flags.append("No response time data for Her (not enough messages)")
    elif her_response > 60:
        red_flags.append(f"Slow replies from Her ({her_response:.1f} min)")
    if you_response < 5 and len(you_msgs) > 10:
        green_flags.append(f"Quick replies from You ({you_response:.1f} min)")
    if her_response < 5 and len(her_msgs) > 10:
        green_flags.append(f"Quick replies from Her ({her_response:.1f} min)")

    if you_interest < 20 and total_count > 50:
        red_flags.append("Low engagement from You")
    if her_interest < 20 and total_count > 50:
        red_flags.append("Low engagement from Her")
    if you_sentiment["POSITIVE"] > you_sentiment["NEGATIVE"] * 2:
        green_flags.append("Strongly positive tone from You")
    if her_sentiment["POSITIVE"] > her_sentiment["NEGATIVE"] * 2:
        green_flags.append("Strongly positive tone from Her")

    if set(you_emojis) & set(her_emojis):
        similarities.append(f"Shared emojis: {', '.join(set(you_emojis) & set(her_emojis))}")
    if set(you_words) & set(her_words):
        similarities.append(f"Common words: {', '.join(set(you_words) & set(her_words))}")

    result = {
        "messages": [{"timestamp": m["timestamp"].isoformat(), "sender": m["sender"], "content": m["content"]} for m in messages],
        "you": {
            "message_count": len(you_msgs),
            "interest": you_interest,
            "initiations": you_init,
            "top_emojis": you_emojis,
            "top_words": you_words,
            "sentiment": you_sentiment,
            "avg_response_time": you_response
        },
        "her": {
            "message_count": len(her_msgs),
            "interest": her_interest,
            "initiations": her_init,
            "top_emojis": her_emojis,
            "top_words": her_words,
            "sentiment": her_sentiment,
            "avg_response_time": her_response
        },
        "message_count": total_count,
        "conversation_flow": flow_dict,
        "conversation_tone": "Positive" if (you_sentiment["POSITIVE"] + her_sentiment["POSITIVE"]) > (you_sentiment["NEGATIVE"] + her_sentiment["NEGATIVE"]) else "Neutral",
        "love_meter": love_meter,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "similarities": similarities,
        "differences": differences,
        "highlights": {
            "first_message": {"timestamp": first_message["timestamp"].isoformat(), "sender": first_message["sender"], "content": first_message["content"]} if first_message else None,
            "longest_message": {"timestamp": longest_message["timestamp"].isoformat(), "sender": longest_message["sender"], "content": longest_message["content"]} if longest_message else None
        }
    }
    return result

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        chat_file = request.files.get('chat')
        your_name = request.form.get('your_name')
        other_name = request.form.get('other_name')

        if not chat_file or not your_name or not other_name:
            return jsonify({"error": "Missing chat file or names"}), 400

        chat_data = chat_file.read().decode('utf-8', errors='ignore')  # Handle encoding issues
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        messages = loop.run_until_complete(parse_chat(chat_data, your_name, other_name))
        result = loop.run_until_complete(analyze_conversation(messages))
        loop.close()
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {type(e).__name__}: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)