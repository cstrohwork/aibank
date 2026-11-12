# Newsletter activation
Status: website integration and manual draft workflow prepared; no provider account connected, lists created, or emails sent.

## One-time account setup
1. In your Brevo account, create two lists: **CSI Daily Market Brief** and **CSI Week in Review**. Contacts choosing both belong to both lists in a single contact database.
2. Create a hosted signup form with required email; optional first name and company; and a required multi-list subscription block for those two lists. Selecting both subscribes to both. Enable double confirmation, CAPTCHA, and consent text explaining the publications and unsubscribe option. Set the confirmation redirect to https://ainvestmentbank.ai/CapitalSignal/subscribe/.
3. Retain signup time, source, confirmation status and preferences in Brevo. Confirm that unconfirmed contacts never enter the distribution lists. Test Daily only, Weekly only, and Both with addresses you control.
4. Paste the published HTTPS sibforms.com form URL into CapitalSignal/subscribe/config.json as signupUrl. The website activates its signup button only for a valid provider form URL.
5. Verify the sending domain and sender in Brevo using the DNS records it supplies. Use a monitored reply mailbox. Supply the business postal address in the campaign footer.
6. Add GitHub Actions secret BREVO_API_KEY. Add repository variables BREVO_DAILY_LIST_ID, BREVO_WEEKLY_LIST_ID, NEWSLETTER_SENDER_EMAIL, NEWSLETTER_POSTAL_ADDRESS. Never commit API keys, subscriber exports, or addresses of subscribers.
7. In GitHub Actions, run **Prepare newsletter email draft** with daily or weekly and the date of an existing, reviewed edition. This creates a branded email linking to that exact edition. It does not send. Re-running creates another draft; check existing drafts first.
8. In Brevo, inspect recipient list, send yourself a preview, check links and unsubscribe, then approve the first sends. Test opt-out suppression and preference changes before using real subscribers.

## Ongoing publishing
Publish the website edition first, verify the public URL, then prepare its email draft. Existing website publication jobs are untouched. Automatic delivery is not enabled: connect it only after initial sends are validated and duplicate-send protection is in place.

Subscription links are separate from the approved three-link header so the banner layout remains intact. Carry the subscription footer into future edition generators.

## Reference
- Signup forms and double confirmation: https://help.brevo.com/hc/en-us/articles/208771869-Create-a-sign-up-form-in-Brevo
- Multi-list preferences: https://help.brevo.com/hc/en-us/articles/360000545200-Enable-your-contacts-to-subscribe-or-unsubscribe-from-specific-lists-using-a-form-multi-list-subscriptions
- Campaign API: https://developers.brevo.com/reference/create-email-campaign
