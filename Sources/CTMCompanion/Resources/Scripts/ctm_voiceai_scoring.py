import requests
import csv
import time
from openai import OpenAI

# ------------------- VOICE AI INSTRUCTIONS -------------------
VOICE_AI_INSTRUCTIONS = """
{{INSTRUCTIONS FROM CTM VOICEAI USR CONFIG}}
"""

# ------------- CONFIGURATION -------------
OPENAI_API_KEY = "{{OPEN AI KEY}}"
CTM_ACCOUNT_ID = {{CTM ACCT ID}}
CTM_API_TOKEN = '{{CTM BASIC AUTH}}'
AGENT_ID = '{{CTM VOICEAI USR ID}}'
CSV_FILE = 'ctm_ai_analysis.csv'
OPENAI_MODEL = 'gpt-4.1-nano'

BASE_URL = f'https://api.calltrackingmetrics.com/api/v1/accounts/{CTM_ACCOUNT_ID}/calls'
HEADERS = {
    'Authorization': 'Basic ' + CTM_API_TOKEN,
    'Accept': 'application/json',
}

client = OpenAI(api_key=OPENAI_API_KEY)

def get_calls_page(agent_id, per_page=100, page=1):
    params = {
        'multi_agents': agent_id,
        'per_page': per_page,
        'page': page
    }
    response = requests.get(BASE_URL, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()

def analyze_transcript_with_openai(transcription_text, summary):
    prompt = f"""
The following are the current prompt instructions used by the Voice AI assistant to guide its behavior:

VOICE_AI_INSTRUCTIONS:
\"\"\"
{VOICE_AI_INSTRUCTIONS}
\"\"\"

Below is a phone call transcript between the Voice AI assistant and a live caller.
Summary of the call: "{summary}"

Transcript text:
\"\"\"
{transcription_text}
\"\"\"

Your tasks:
1. Assess the interaction and extract key information on what occurred in the conversation.
2. Evaluate specifically how closely the Voice AI assistant followed the VOICE_AI_INSTRUCTIONS.
3. Identify any moments where the assistant deviated from the instructions or could have been improved, especially regarding conversational flow, clarity, call control, and caller satisfaction.
4. Listen for awkward transitions, points of caller confusion, or other interaction issues.
5. **Provide at least two specific, actionable recommendations for updating or fine-tuning the VOICE_AI_INSTRUCTIONS prompt to improve future outcomes.** These recommendations should be clear and refer to the instruction text above.
6. Write your feedback using clear bullet points.

Please provide your analysis and detailed, actionable prompt improvement suggestions below:
"""
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API request failed: {e}")
        return "OpenAI API request failed."

def main():
    print("Starting to collect CTM calls...")
    all_calls = []
    page = 1

    while True:
        data = get_calls_page(AGENT_ID, per_page=100, page=page)
        print("\n==== RAW API RESPONSE DUMP ====")
        print(data)
        print("==== END RAW API RESPONSE DUMP ====")

        # Try to find call list by key or top-level values
        if isinstance(data, list):
            calls = data
        elif 'calls' in data:
            calls = data['calls']
        elif 'activities' in data:
            calls = data['activities']
        elif 'results' in data:
            calls = data['results']
        else:
            calls = []
            for v in data.values():
                if isinstance(v, list) and v and isinstance(v[0], dict) and 'id' in v[0]:
                    calls = v
                    break

        print("DEBUG: Found {} calls on page {}".format(len(calls), page))

        if not calls:
            print(f"No calls found on page {page}")
            break

        print(f"Page {page} - Retrieved {len(calls)} calls")
        for call in calls:
            call_id = call.get('id')
            transcript_text = call.get('transcription_text', '')
            summary = call.get('summary', '')
            if not transcript_text:
                print(f"Call {call_id} has no transcription text - skipping OpenAI analysis")
                assessment = ""
            else:
                print(f"Analyzing call id {call_id} with OpenAI...")
                assessment = analyze_transcript_with_openai(transcript_text, summary)
                time.sleep(1)

            all_calls.append({
                "id": call_id,
                "transcription_text": transcript_text,
                "summary": summary,
                "openai_analysis": assessment
            })

        total_pages = data.get('total_pages', 1)
        if page >= total_pages:
            print("Reached last page.")
            break
        page += 1

    # Write to CSV
    print(f"Writing results to {CSV_FILE} ...")
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['id', 'transcription_text', 'summary', 'openai_analysis']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in all_calls:
            writer.writerow(entry)
    print("Done.")

if __name__ == '__main__':
    main()
