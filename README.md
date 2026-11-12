# Royalty Loom

Turn a signed royalty agreement and a sales export into to-the-cent creator statements, then pay everyone through PayPal after one human authorization.

Royalty Loom is a local royalties desk for small creative teams: a band, an illustrator and a writer, a few people selling a digital product. It is organized around four jobs: **Statement**, **Sales**, **Splits** and **Payouts**. Each collaborator can see the sentence in the agreement that gives them their share, which sales and deductions produced the amount, and what the payment provider reported.

## How it uses AI

A language model reads the agreement and returns, for each named collaborator, only a name and the exact sentence that gives their share. The application restores the original wording, derives the percentage from that quotation, and shows the complete agreement beside it. A person confirms that the shares apply to the reporting period before they are used.

The model never produces amounts and never authorizes a payment. Shares and money are computed by deterministic code in integer cents. Agreements the supported model cannot represent (conditions, tiers, undefined terms) are sent to manual review.

Any OpenAI-compatible chat endpoint works. It was built and tested with a local Qwen 2.5 model served by Ollama or llama.cpp. Manual entry works with no model at all.

## How it uses PayPal

Payments run on the PayPal REST API in **Sandbox**:

- OAuth 2.0 client credentials (`/v1/oauth2/token`), kept on the server only
- Payouts API: `POST /v1/payments/payouts` creates one batch with one item per creator, after the operator ticks an approval box and types the authorization
- `GET /v1/payments/payouts/{batch_id}` reads the batch and each item's status back, so the statement and the money always agree
- Every batch carries a durable sender batch ID, so a retry cannot pay twice. If a response is lost, the result is treated as unknown and recovered by looking up the original batch, never by sending again

## Run it

Requires Python 3.10 or newer. There are no packages to install.

Explore the built-in example (no accounts needed):

```sh
python3 app.py
# the address is printed; the default is http://127.0.0.1:8733
```

Run with PayPal Sandbox and a local model:

```sh
ollama pull qwen2.5:7b

export PAYPAL_CLIENT_ID="your sandbox client id"
export PAYPAL_CLIENT_SECRET="your sandbox client secret"
export PAYPAL_BASE_URL="https://api-m.sandbox.paypal.com"
export ROYALTY_LOOM_SANDBOX_PAYOUTS=1
export ROYALTY_LOOM_AI_URL="http://127.0.0.1:11434/v1/chat/completions"
export ROYALTY_LOOM_AI_MODEL="qwen2.5:7b"
export ROYALTY_LOOM_DB="$HOME/.royalty-loom/desk.sqlite"

python3 app.py --port 8733
```

Create Sandbox credentials at <https://developer.paypal.com/dashboard/applications/sandbox> and enable Payouts for the application. Use Sandbox personal accounts as recipients to see payments complete.

Options: `--no-browser` runs the server only, `--port 0` picks a free port.

## A two-minute walkthrough

1. Choose **Use your project**, name it, paste the royalty agreement and set the reporting period.
2. Open **Local AI options** and choose **Suggest splits from agreement**. Read each quoted share against the full text, tick the review box and choose **Use these shares**.
3. Add each creator's recipient email.
4. In **Sales**, import the period's CSV (`id,type,amount,description`, or map your own columns) and calculate the statement.
5. Open any creator's private statement, or download them all.
6. In **Payouts**, tick the approval box, type `AUTHORIZE SANDBOX` and authorize. The batch ID appears, and **Refresh status** reads each payment back from PayPal.

`examples/` contains a sample store export.

## Tests

```sh
python3 -m unittest discover -s . -p "test_*.py"
```

One process-management test in `test_local_ai_runtime.py` assumes Linux.

## License

MIT. See [LICENSE](LICENSE). The bundled Bricolage Grotesque font is under the SIL Open Font License (`fonts/OFL.txt`).

Source: <https://github.com/Jacob-Met/royaltyloom-app>
