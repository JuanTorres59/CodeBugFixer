import os

from flask import Flask, abort, request, render_template
from openai import OpenAI
import hashlib
import sqlite3
import stripe

try:
    import config  # type: ignore
except Exception:  # pragma: no cover
    config = None

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or (getattr(config, "API_KEY", None) if config else None)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY") or (
    getattr(config, "STRIPE_TEST_KEY", None) if config else None
)
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY") or (
    getattr(config, "STRIPE_PUBLISHABLE_KEY", None) if config else None
) or "pk_test_51SgzAwDswM9mzDDUVTtngkGL6igBwVKaLzhcgoszBpirsgFBCC2A8trfYjlmESTNQoRvNMqOfEmaJKnDCiEFS43h00NpzuqNkB"

def get_openai_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing OpenAI API key. Set OPENAI_API_KEY (recommended) or define API_KEY in config.py.")
    return OpenAI(api_key=OPENAI_API_KEY)


def configure_stripe() -> None:
    if not STRIPE_SECRET_KEY:
        raise RuntimeError(
            "Missing Stripe secret key. Set STRIPE_SECRET_KEY (recommended) or define STRIPE_TEST_KEY in config.py."
        )
    stripe.api_key = STRIPE_SECRET_KEY

PLAN_AMOUNTS_USD_CENTS = {
    "monthly": 500,
    "quarterly": 1200,
    "annual": 4500,
}

def initialize_database():
    conn = sqlite3.connect('app.db')
    c = conn.cursor()
    c.execute(
        '''CREATE TABLE IF NOT EXISTS users (fingerprint text primary key, usage_counter int)''')
    conn.commit()
    conn.close()
    
def get_fingerprint():
    browser = request.user_agent.browser
    version = request.user_agent.version and float(request.user_agent.version.split(".")[0])
    platform = request.user_agent.platform
    string = f"{browser}:{version}:{platform}"
    fingerprint = hashlib.sha256(string.encode("utf-8")).hexdigest()
    print(fingerprint)
    return fingerprint

def get_usage_counter(fingerprint):
    conn = sqlite3.connect('app.db')
    c = conn.cursor()
    result = c.execute('SELECT usage_counter FROM users WHERE fingerprint=?', [fingerprint]).fetchone()
    conn.close()
    if result is None:
        conn = sqlite3.connect('app.db')
        c = conn.cursor()
        c.execute('INSERT INTO users (fingerprint, usage_counter) VALUES (?, 0)', [fingerprint])
        conn.commit()
        conn.close()
        return 0
    else:
        return result[0]
    
def update_usage_counter(fingerprint, usage_counter):
    conn = sqlite3.connect('app.db')
    c = conn.cursor()
    c.execute('UPDATE users SET usage_counter=? WHERE fingerprint=?', [usage_counter, fingerprint])
    conn.commit()
    conn.close()

@app.route("/", methods = ["GET", "POST"])
def index():
    initialize_database()
    fingerprint = get_fingerprint()
    usage_counter = get_usage_counter(fingerprint)
    
    if request.method == "POST":
        if usage_counter > 3:
            return render_template("payment.html", stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)
        code = request.form["code"]
        error = request.form["error"]
        prompt = (f"Explain the error in this code without fixing it:"
                  f"\n\n{code}\n\nError:\n\n{error}")
        model_engine = "gpt-3.5-turbo"

        try:
            client = get_openai_client()
        except RuntimeError as exc:
            abort(500, description=str(exc))
        
        explanation_completions = client.chat.completions.create(
            model = model_engine,
            messages= [{"role" : "user", "content" : f"{prompt}"}],
            max_tokens=1024,
            n=1,
            stop=None,
            temperature=0.2,
        )
        
        explanation = explanation_completions.choices[0].message.content
        fixed_code_prompt = (f"Fix this code: \n\n{code}\n\nError:\n\n{error}."
                             f"\n Respond only with the fixed code.")
        fixed_code_completions = client.chat.completions.create(
            model=model_engine,
            messages=[{"role":"user", "content" : f"{fixed_code_prompt}"}],
            max_tokens=1024,
            n=1,
            stop=None,
            temperature=0.2,
        )
        fixed_code = fixed_code_completions.choices[0].message.content
        usage_counter += 1
        print(usage_counter)
        update_usage_counter(fingerprint, usage_counter)
        
        return render_template("index.html", explanation = explanation, fixed_code = fixed_code)
    return render_template("index.html")

@app.route("/charge", methods=["POST"])
def charge():
    plan = (request.form.get("plan") or "").strip().lower()
    if plan not in PLAN_AMOUNTS_USD_CENTS:
        abort(400, description="Unknown plan.")
    amount = PLAN_AMOUNTS_USD_CENTS[plan]

    stripe_email = request.form.get("stripeEmail")
    stripe_token = request.form.get("stripeToken")
    if not stripe_email or not stripe_token:
        abort(400, description="Missing Stripe token.")

    try:
        configure_stripe()
    except RuntimeError as exc:
        abort(500, description=str(exc))

    customer = stripe.Customer.create(
        email=stripe_email,
        source=stripe_token,
    )
    charge = stripe.Charge.create(
        customer=customer.id,
        amount=amount,
        currency="usd",
        description="App Charge"
    )
    return render_template("charge.html", amount = amount, plan=plan)
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
    
