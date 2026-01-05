# Code Bug Fixer

## Project Overview
Code Bug Fixer is a small Flask web app where you paste a code snippet + an error message and get back an explanation and a proposed fix using the OpenAI API. It’s built for developers who want a fast second opinion while debugging. It also includes a simple Stripe paywall after a limited number of free runs.

## Why I Built This
I built this to learn how to ship a full loop: a web UI → backend → LLM API call → readable output. I also wanted hands-on experience with integrating Stripe checkout and deploying a Python app to Azure App Service.

## Key Features
- Paste code + stack trace and get an explanation + fixed code
- Simple usage metering stored in SQLite (per browser fingerprint)
- Paywall page with Stripe Checkout for upgrading
- Copy/download-friendly output UI (tabs + diff view)
- Dark mode toggle (client-side)

## Tech Stack
- Python 3 / Flask
- HTML/CSS/Vanilla JS (Jinja templates)
- OpenAI API (chat completions)
- Stripe API + Stripe Checkout
- SQLite (local usage counter)
- Azure App Service (deployment target)

## High-Level How It Works
The frontend is a single-page form that POSTs `code` and `error` to the Flask backend. The server checks a local usage counter (SQLite) and, if within the free limit, calls the OpenAI API twice: one prompt for an explanation and another for a corrected version of the code. The results are rendered back into the same template with tabs for Explanation / Fixed Code / Diff. Once free credits are exhausted, the app redirects users to `/payment`, which launches Stripe Checkout and then posts to `/charge` to create a test-mode charge.

## What I Learned
- LLM UX matters: prompt shaping, output formatting, and failure states are as important as the API call
- Paywalls need server-side validation (e.g., don’t trust client-provided amounts)
- Deploying to Azure surfaced real-world constraints (timeouts, logging, env vars)
- Small “polish” features (copy, download, tabs, keyboard shortcuts) change usability a lot

## Status
Functional prototype, deployed on Azure.

## Demo
Live: http://codebugfixer-aura-jdt-001.azurewebsites.net
Repo: https://github.com/Jdtorres59/CodeBugFixer.git
