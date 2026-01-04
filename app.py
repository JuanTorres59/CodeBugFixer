import os
import logging
import time
import uuid

from flask import Flask, abort, request, render_template
from openai import OpenAI
import hashlib
import sqlite3
import stripe

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("codebugfixer")

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
    timeout_s = float(os.getenv("OPENAI_TIMEOUT", "30"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
    return OpenAI(api_key=OPENAI_API_KEY, timeout=timeout_s, max_retries=max_retries)


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

FREE_FIX_LIMIT = 10

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
    credits_remaining = max(0, FREE_FIX_LIMIT - usage_counter)
    
    if request.method == "POST":
        request_id = uuid.uuid4().hex[:8]
        if usage_counter >= FREE_FIX_LIMIT:
            return render_template(
                "payment.html",
                stripe_publishable_key=STRIPE_PUBLISHABLE_KEY,
                credits_remaining=credits_remaining,
            )

        code = (request.form.get("code") or "").strip()
        error = (request.form.get("error") or "").strip()
        language = (request.form.get("language") or "auto").strip()
        tone = (request.form.get("tone") or "concise").strip()

        logger.info(
            "[%s] / POST received lang=%s tone=%s credits_remaining=%s code_len=%s error_len=%s",
            request_id,
            language,
            tone,
            credits_remaining,
            len(code),
            len(error),
        )

        if not code or not error:
            return render_template(
                "index.html",
                code_input=code,
                error_input=error,
                language=language,
                tone=tone,
                credits_remaining=credits_remaining,
                ui_error="Paste both your code and the error message to continue.",
            )

        prompt = (f"Explain the error in this code without fixing it:"
                  f"\n\n{code}\n\nError:\n\n{error}")
        if language and language != "auto":
            prompt += f"\n\nLanguage: {language}"
        prompt += "\n\nWrite the explanation in a developer-friendly way."
        if tone == "detailed":
            prompt += " Be detailed and structured."
        else:
            prompt += " Be concise."
        model_engine = "gpt-3.5-turbo"

        try:
            client = get_openai_client()
        except RuntimeError as exc:
            logger.error("[%s] OpenAI client init failed: %s", request_id, exc)
            return render_template(
                "index.html",
                code_input=code,
                error_input=error,
                language=language,
                tone=tone,
                credits_remaining=credits_remaining,
                ui_error=str(exc),
            )
        
        try:
            t0 = time.time()
            explanation_completions = client.chat.completions.create(
                model=model_engine,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                n=1,
                stop=None,
                temperature=0.2,
            )
        except Exception as exc:
            logger.exception("[%s] OpenAI explanation request failed", request_id)
            return render_template(
                "index.html",
                code_input=code,
                error_input=error,
                language=language,
                tone=tone,
                credits_remaining=credits_remaining,
                ui_error=f"OpenAI request failed: {exc}",
            )
        finally:
            try:
                logger.info("[%s] OpenAI explanation elapsed=%.2fs", request_id, time.time() - t0)  # type: ignore[name-defined]
            except Exception:
                pass
        
        explanation = explanation_completions.choices[0].message.content
        fixed_code_prompt = (f"Fix this code: \n\n{code}\n\nError:\n\n{error}."
                             f"\n Respond only with the fixed code.")

        if language and language != "auto":
            fixed_code_prompt += f"\nLanguage: {language}"
        if tone == "detailed":
            fixed_code_prompt += "\nKeep formatting clean and include any necessary imports."

        try:
            t1 = time.time()
            fixed_code_completions = client.chat.completions.create(
                model=model_engine,
                messages=[{"role": "user", "content": fixed_code_prompt}],
                max_tokens=1024,
                n=1,
                stop=None,
                temperature=0.2,
            )
        except Exception as exc:
            logger.exception("[%s] OpenAI fixed-code request failed", request_id)
            return render_template(
                "index.html",
                code_input=code,
                error_input=error,
                language=language,
                tone=tone,
                credits_remaining=credits_remaining,
                ui_error=f"OpenAI request failed: {exc}",
            )
        finally:
            try:
                logger.info("[%s] OpenAI fixed-code elapsed=%.2fs", request_id, time.time() - t1)  # type: ignore[name-defined]
            except Exception:
                pass

        fixed_code = fixed_code_completions.choices[0].message.content
        usage_counter += 1
        update_usage_counter(fingerprint, usage_counter)
        credits_remaining = max(0, FREE_FIX_LIMIT - usage_counter)

        logger.info("[%s] request complete credits_remaining=%s", request_id, credits_remaining)
        
        return render_template(
            "index.html",
            code_input=code,
            error_input=error,
            language=language,
            tone=tone,
            credits_remaining=credits_remaining,
            explanation=explanation,
            fixed_code=fixed_code,
        )

    return render_template(
        "index.html",
        credits_remaining=credits_remaining,
        language="auto",
        tone="concise",
    )


@app.route("/payment", methods=["GET"])
def payment():
    initialize_database()
    fingerprint = get_fingerprint()
    usage_counter = get_usage_counter(fingerprint)
    credits_remaining = max(0, FREE_FIX_LIMIT - usage_counter)
    logger.info("/payment GET credits_remaining=%s", credits_remaining)
    return render_template(
        "payment.html",
        stripe_publishable_key=STRIPE_PUBLISHABLE_KEY,
        credits_remaining=credits_remaining,
    )

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

    logger.info("/charge POST plan=%s amount=%s", plan, amount)
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
    
