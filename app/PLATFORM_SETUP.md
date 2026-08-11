# Social Platform Setup — 8 Pillars LeadBot v3.1

## Nextdoor
Use approved Nextdoor developer access. Configure `NEXTDOOR_ACCESS_TOKEN` and the Search Posts endpoint. LeadBot searches each target city every 30 minutes for concrete, driveway, patio, foundation, slab, sidewalk, pool deck, and patio-cover terms and asks the API to include comments. Any phone/email published in returned post/comment text is extracted. If no phone/email is public, the original post and public poster identity are kept as the reply route.

## Facebook / Instagram DMs
Use a Meta business app connected to the 8 Pillars Facebook Page / Instagram Professional account. Point the Messenger/Instagram webhook callback to:

`https://YOUR-HOST/webhooks/meta`

Set `META_VERIFY_TOKEN` to the verification token you configure in Meta and `META_APP_SECRET` to enable `X-Hub-Signature-256` validation. Incoming concrete-request DMs are treated as `DIRECT_DM` leads and can alert immediately.

## TikTok public requests
LeadBot runs dedicated fresh public-web searches restricted to `tiktok.com` every 30 minutes. It extracts public usernames, captions/snippets, phone/email if actually published, city, scope, dimensions, and the original video/profile route.

TikTok does not expose an unrestricted commercial keyword-search endpoint for every organic TikTok video. Do not use private scraping/login bypasses; they are brittle and can get accounts blocked.

## TikTok Business DMs
Authorize the 8 Pillars TikTok Business Account for TikTok Business Messaging API and point the message webhook to:

`https://YOUR-HOST/webhooks/tiktok?token=YOUR_PRIVATE_WEBHOOK_TOKEN`

Set the same token in `WEBHOOK_SHARED_SECRET`. Incoming business messages that mention concrete work are inserted as `DIRECT_DM` leads.

## Social/email fallback
Connect an inbox using IMAP. LeadBot scans notification emails for terms such as `new message`, `sent you a message`, `replied to your post`, `concrete`, `driveway`, `patio`, `slab`, and `foundation`. This is useful for marketplaces and platforms that send prompt email notifications but do not expose a practical API.

## Contactability
LeadBot only pushes HOT notifications by default when a lead has one of:
- `DIRECT`: public phone and/or email.
- `DIRECT_DM`: inbound message to an authorized business account.
- `SOCIAL_DM`: a direct original social post/profile route suitable for messaging.

Hidden private phone numbers, personal emails, or residential addresses are not reverse-identified. A project address is captured only when it is explicitly published for the job or supplied by the prospect.
