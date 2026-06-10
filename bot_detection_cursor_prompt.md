# Bot Detection Guide — Facebook, TikTok, Instagram, X, Reddit

## Preface: The Golden Rule of Bot Detection

**No single signal is enough. Bots are caught by signal stacking.**

One weak signal = noise. Two = suspicious. Three or more converging signals = high confidence bot.
Modern bots (especially AI-powered ones in 2025/2026) are designed to evade single-signal detectors.
Your scoring system must be additive — each signal adds weight to a verdict, never decides it alone.

---

## Universal Signals (Apply to All Platforms)

These apply regardless of platform. Score them first, then layer platform-specific signals on top.

### Account Identity Signals
| Signal | Bot Pattern | Weight |
|---|---|---|
| **Profile picture** | Missing, AI-generated stock face, reused across accounts | Medium |
| **Username** | Random alphanumeric strings (`user_48291x`), name+number combos | Medium |
| **Display name** | Sentence-length name, emoji spam, keyword stuffing | Medium |
| **Bio** | Empty, or keyword-stuffed with crypto/Telegram/WhatsApp links | High |
| **Account age vs. activity** | 90-day-old account with thousands of posts/followers | High |

### Behavioral Signals
| Signal | Bot Pattern | Weight |
|---|---|---|
| **Posting velocity** | Posting more than humanly possible (e.g. 100+ posts/day) | High |
| **Posting schedule** | Activity at exact intervals, 24/7 activity with no breaks | High |
| **Content diversity** | Every post identical template, same hashtag sets | High |
| **Reply speed** | Replying to threads within seconds of posting | High |
| **Engagement ratio** | Massive following but near-zero engagement on own content | High |
| **Content originality** | Copy-pasted content across multiple accounts | High |

### Network Signals
| Signal | Bot Pattern | Weight |
|---|---|---|
| **Follower/following ratio** | Following >> followers, or following at ceiling (5000/5000) | Medium |
| **Follower quality** | Own followers are also bots (recursive bot networks) | High |
| **Coordinated behavior** | Multiple accounts posting identical content within seconds | Critical |

---

## Platform-Specific Detection

---

### 1. X (Twitter/X)

X is the most researched platform for bot detection. Data is richest here.

#### API Fields to Pull
```
GET /2/users/{id}?user.fields=created_at,public_metrics,description,
    profile_image_url,verified,entities,withheld,pinned_tweet_id
GET /2/users/{id}/tweets?tweet.fields=created_at,source,
    public_metrics,referenced_tweets&max_results=100
```

#### Signal Scoring

**Account-Level Signals**

| Signal | How to Detect | Weight |
|---|---|---|
| Account age < 90 days | `created_at` field | Medium |
| No profile image | `profile_image_url` is default egg/blank | Medium |
| Username is random chars | Regex: `^[a-z]+\d{4,}$` or 15+ char random strings | Medium |
| Bio contains Telegram/WhatsApp links | Regex on `description` field | High |
| AI buzzword clustering in bio | NLP check for "crypto", "NFT", "DM for collab" clusters | Medium |
| Follower:following ratio < 0.1 | `followers_count / following_count` | High |
| Following count near 5000 (platform ceiling) | `following_count >= 4900` | High |
| Not listed by anyone | `listed_count == 0` with >1 year age | Medium |
| Zero or <5 original tweets ever | `tweet_count` in public metrics | High |

**Behavioral Signals (from tweet history)**

| Signal | How to Detect | Weight |
|---|---|---|
| Posting from automation tools | `source` field: "IFTTT", "Zapier", "Hootsuite API" | High |
| Sub-30-second reply gaps | Calculate median time between reply tweets | High |
| 24/7 posting activity | Histogram of `created_at` hours — no natural sleep gap | High |
| >50 tweets/day sustained | Count tweets per day across history | High |
| Identical tweet text duplicated | Hash tweet content, check duplicates | High |
| Retweet-only account | >95% of tweets are retweets, 0 original content | Medium |
| Hidden unicode characters | Scan tweet text for zero-width characters (bot fingerprints) | High |
| Sycophantic openers | "Great point!", "Absolutely!", "Well said!" as first words | Medium |
| Em-dash abuse (AI writing tell) | Disproportionate use of `—` in text | Low |

**Scoring Thresholds for X**
```
0-2 signals:   HUMAN (likely)
3-4 signals:   SUSPICIOUS — flag for review
5+ signals:    BOT (high confidence)
Any Critical:  BOT — coordinated activity is near-certain automation
```

---

### 2. Reddit

Reddit has the most unique bot detection context — community governance matters as much as technical signals.

#### API Fields to Pull
```
GET /user/{username}/about.json
    → created_utc, link_karma, comment_karma, is_employee,
      has_verified_email, icon_img, subreddit (profile info)

GET /user/{username}/submitted.json?limit=100
GET /user/{username}/comments.json?limit=100
```

#### Signal Scoring

**Account-Level Signals**

| Signal | How to Detect | Weight |
|---|---|---|
| Account age < 30 days | `created_utc` | Medium |
| No email verification | `has_verified_email == false` | Medium |
| Zero or negative karma | `link_karma + comment_karma <= 0` | Medium |
| Karma velocity spikes | 500+ karma gained in <1 hour from karma-farm subs | High |
| Default profile icon | `icon_img` is Reddit's default avatar | Low |
| Username is random chars | Same regex as X | Medium |

**Behavioral Signals (from post/comment history)**

| Signal | How to Detect | Weight |
|---|---|---|
| Posting in unrelated subreddits rapidly | Multiple different subs within minutes | High |
| Template-based comments | Cosine similarity > 0.9 across multiple comments | High |
| Comments at exact intervals | Variance in post timing < 5 seconds | High |
| Only posts links (never comments) | `link_karma >> comment_karma` with zero organic discussion | Medium |
| Karma-farming subreddits in history | Detect posts in r/FreeKarma4U, r/karma, etc. | High |
| Cross-posts identical content | Same text/link across multiple subs same day | High |
| Low CQS indicators | Consistently downvoted, posts collapsed, limited visibility | High |
| No community participation | Zero replies to their own posts/comments | Medium |
| New account posting in restricted subs | Account too new for sub's karma/age requirements — keep trying | Medium |

**Reddit-Specific Context**
Reddit's Contributor Quality Score (CQS) is the most reliable internal signal. While you can't read it directly from the API, you can infer it:
- Accounts with low CQS have their posts auto-collapsed or invisible to logged-out users
- Check if the account's posts appear when logged out vs logged in — invisible = low CQS
- Low CQS accounts can still post, but nothing reaches anyone (shadow suppression)

**Scoring Thresholds for Reddit**
```
0-2 signals:   HUMAN (likely)
3-4 signals:   SUSPICIOUS
5+ signals:    BOT (high confidence)
New account + karma farming subs + template comments = BOT immediately
```

---

### 3. TikTok

TikTok's API access is limited. Detection relies more on scraped profile data and behavioral inference.

#### Data Available
```
GET https://www.tiktok.com/@{username} (scrape)
    → follower_count, following_count, video_count, like_count,
      bio, profile_image, verified status, account creation hints
```

TikTok does not expose `created_at` via public API — infer account age from earliest video upload date.

#### Signal Scoring

**Account-Level Signals**

| Signal | How to Detect | Weight |
|---|---|---|
| No profile picture | Scrape `og:image` — default TikTok avatar | Medium |
| Bio is empty or keyword spam | Scrape bio text | Medium |
| Zero videos posted | `video_count == 0` — account exists only to engage | High |
| Follower:following ratio < 0.05 | Standard ratio math | High |
| Account age (from earliest video) < 30 days | Date of first uploaded video | Medium |
| Verified badge missing + massive following | Unverified account with 100k+ followers and no content | High |

**Behavioral Signals**

| Signal | How to Detect | Weight |
|---|---|---|
| Engagement rate < 0.5% | `(likes + comments) / followers * 100` | High |
| All comments generic | "So cute!", "Love this!", "Amazing!" with no specificity | High |
| Comment timestamps cluster together | Multiple identical comments within seconds | High |
| Views >> likes ratio is inverted | More comments than views (purchased engagement) | High |
| No original sound usage | Every video uses trending sounds only — no authentic audio | Low |
| Follower growth spikes | Sudden +10k follower jump with no viral content | High |
| Engagement inconsistency | Reels/videos average wildly different engagement per content type | Medium |

**TikTok-Specific Note**
TikTok does not expose detailed activity history via public API. The most reliable signal here is the engagement rate calculation combined with comment quality analysis. Scrape 20-30 comments from recent videos and run them through Claude to assess authenticity.

**Scoring Thresholds for TikTok**
```
0-2 signals:   HUMAN (likely)
3-4 signals:   SUSPICIOUS
5+ signals:    BOT (high confidence)
Zero videos + massive following = BOT immediately
```

---

### 4. Instagram

Instagram's Graph API requires business account access. Public scraping is the fallback.

#### Data Available (Public Scrape)
```
GET https://www.instagram.com/{username}/?__a=1&__d=dis
    → follower_count, following_count, media_count, bio,
      profile_pic_url, is_verified, is_private, full_name
```

Or via Graph API (if you have access):
```
GET /{user-id}?fields=followers_count,follows_count,media_count,
    biography,profile_picture_url,username,website,account_type
```

#### Signal Scoring

**Account-Level Signals**

| Signal | How to Detect | Weight |
|---|---|---|
| Default/stock profile picture | Reverse image search or perceptual hash check | Medium |
| Bio contains external links to known spam domains | URL check against blocklist | High |
| Account private + following thousands | Private accounts that mass-follow then unfollow | Medium |
| Username pattern | Same regex as X | Medium |
| No posts / very few posts | `media_count == 0` or < 3 with thousands of followers | High |
| Follower:following ratio < 0.1 | Standard math | High |

**Behavioral Signals**

| Signal | How to Detect | Weight |
|---|---|---|
| Engagement rate < 1% for <10k accounts | `(avg_likes + avg_comments) / followers * 100` | High |
| Save-to-like ratio is 0 | Real followers save content — zero saves = bot audience | High |
| Comments are generic or emoji-only | Analyze comment text quality | High |
| Follower location vs. content niche mismatch | Audience insights location vs. posted content language | High |
| Sudden follower spikes | +5000 followers in a day with no viral post | High |
| Follow/unfollow pattern | Following 1000s, then unfollowing — scrape following list over time | High |
| Story views >> post likes | Bots that view stories but don't engage with posts | Medium |

**Engagement Rate Benchmarks (2025/2026)**
```
Nano (< 1K):    5–8% = healthy
Micro (1K-10K): 3–6% = healthy
Mid (10K-100K): 2–4% = healthy
Macro (100K+):  1–3% = healthy

< 0.5% at any tier = suspicious
< 0.1% = near-certain bot audience
```

**Scoring Thresholds for Instagram**
```
0-2 signals:   HUMAN (likely)
3-4 signals:   SUSPICIOUS
5+ signals:    BOT (high confidence)
Zero posts + thousands of followers + generic bio = BOT immediately
```

---

### 5. Facebook

Facebook is the hardest platform to automate detection on — the API is the most restricted.

#### Data Available
```
Public profile scrape or Graph API (requires app review):
    → name, follower_count, friend_count, about, profile_picture,
      page_category (for pages), creation_date (pages only), post history
```

#### Signal Scoring

**Account-Level Signals**

| Signal | How to Detect | Weight |
|---|---|---|
| Account creation date is very recent | Graph API `created_time` (pages only) or infer from earliest post | High |
| Profile picture is AI-generated | Run image through AI detection tool or perceptual hash | High |
| Name follows bot pattern | Unusual name combinations, extra middle names, numbers | Medium |
| No profile cover photo | Missing = low effort account | Low |
| Very few friends/followers | Account exists only to post, not connect | Medium |
| Location inconsistency | Claims to be from one country, posts in another language | Medium |

**Behavioral Signals**

| Signal | How to Detect | Weight |
|---|---|---|
| Posts at machine-like intervals | Exactly every X hours — no human would do this | High |
| Shares only external links | Never original content, only link reposts | High |
| Comments are template-based | Same comment text across many posts | High |
| Joins many groups rapidly | Joining 50 groups in a day | High |
| Posts same content across multiple groups | Identical text/image copy-pasted | Critical |
| Zero personal photos | No life photos, events, tagged friends — only promotional posts | High |
| Engagement is mostly from other bot-pattern accounts | Recursive bot network detection | High |
| Page likes from high-bot countries disproportionately | Audience location vs. page language/topic mismatch | Medium |

**Facebook-Specific Note**
Facebook bots often operate as Pages rather than personal accounts. For Pages, `created_time` is available via API and is the single most reliable signal — a Page created last month with 50k followers is almost certainly inauthentic.

**Scoring Thresholds for Facebook**
```
0-2 signals:   HUMAN (likely)
3-4 signals:   SUSPICIOUS
5+ signals:    BOT (high confidence)
Recently created + mass followers + link-only posts = BOT immediately
```

---

## Implementation: `core/bot_detector.py`

### Data Model

```python
from dataclasses import dataclass, field
from enum import Enum


class BotVerdict(str, Enum):
    HUMAN = "HUMAN"
    SUSPICIOUS = "SUSPICIOUS"
    BOT = "BOT"
    UNKNOWN = "UNKNOWN"          # Not enough data to score


@dataclass
class BotSignal:
    name: str                    # e.g. "posting_velocity"
    triggered: bool
    weight: int                  # 1 = low, 2 = medium, 3 = high, 5 = critical
    evidence: str                # Human-readable explanation for the verdict


@dataclass
class BotScore:
    verdict: BotVerdict
    score: int                   # Raw accumulated weight
    confidence: float            # 0.0 - 1.0
    signals: list[BotSignal] = field(default_factory=list)
    platform: str = ""
    username: str = ""
```

### Scoring Engine

```python
VERDICT_THRESHOLDS = {
    # (min_score, min_signals_triggered) → verdict
    "BOT":        (10, 4),
    "SUSPICIOUS": (5,  2),
    "HUMAN":      (0,  0),
}

IMMEDIATE_BOT_PATTERNS = {
    # If ALL conditions in a tuple are true, verdict is BOT regardless of score
    "x":         [("tweet_count_lt_5", "account_age_lt_30", "following_gt_4900")],
    "tiktok":    [("video_count_zero", "followers_gt_10000")],
    "instagram": [("media_count_zero", "followers_gt_5000", "bio_spam")],
    "facebook":  [("created_lt_30_days", "followers_gt_10000", "link_only_posts")],
    "reddit":    [("karma_farm_subs", "template_comments", "account_age_lt_7")],
}


def score_account(signals: list[BotSignal], platform: str, username: str) -> BotScore:
    triggered = [s for s in signals if s.triggered]
    total_score = sum(s.weight for s in triggered)
    signal_count = len(triggered)

    # Check immediate bot patterns first
    triggered_names = {s.name for s in triggered}
    for pattern in IMMEDIATE_BOT_PATTERNS.get(platform, []):
        if all(p in triggered_names for p in pattern):
            return BotScore(
                verdict=BotVerdict.BOT,
                score=total_score,
                confidence=0.97,
                signals=signals,
                platform=platform,
                username=username,
            )

    # Standard threshold scoring
    if total_score >= VERDICT_THRESHOLDS["BOT"][0] and signal_count >= VERDICT_THRESHOLDS["BOT"][1]:
        verdict = BotVerdict.BOT
        confidence = min(0.95, 0.6 + (total_score / 30))
    elif total_score >= VERDICT_THRESHOLDS["SUSPICIOUS"][0]:
        verdict = BotVerdict.SUSPICIOUS
        confidence = min(0.75, 0.4 + (total_score / 20))
    elif signal_count == 0 and total_score == 0:
        verdict = BotVerdict.UNKNOWN
        confidence = 0.0
    else:
        verdict = BotVerdict.HUMAN
        confidence = max(0.5, 1.0 - (total_score / 15))

    return BotScore(
        verdict=verdict,
        score=total_score,
        confidence=confidence,
        signals=signals,
        platform=platform,
        username=username,
    )
```

### Per-Platform Detectors

Each detector returns a `BotScore`. Structure each as `detect_{platform}(account_data: dict) -> BotScore`.

```python
def detect_x(account_data: dict) -> BotScore:
    signals = []

    # Account age
    age_days = (now - account_data["created_at"]).days
    signals.append(BotSignal(
        name="account_age_lt_90",
        triggered=age_days < 90,
        weight=2,
        evidence=f"Account is {age_days} days old"
    ))

    # Tweet count
    tweet_count = account_data.get("tweet_count", 0)
    signals.append(BotSignal(
        name="tweet_count_lt_5",
        triggered=tweet_count < 5,
        weight=3,
        evidence=f"Only {tweet_count} total tweets"
    ))

    # Follower ratio
    followers = account_data.get("followers_count", 0)
    following = account_data.get("following_count", 1)
    ratio = followers / following if following > 0 else 0
    signals.append(BotSignal(
        name="low_follower_ratio",
        triggered=ratio < 0.1 and following > 100,
        weight=3,
        evidence=f"Follower:following ratio is {ratio:.2f}"
    ))

    # Following ceiling
    signals.append(BotSignal(
        name="following_gt_4900",
        triggered=following >= 4900,
        weight=3,
        evidence=f"Following {following} accounts (near platform ceiling)"
    ))

    # Bio spam
    bio = account_data.get("description", "")
    spam_terms = ["telegram", "whatsapp", "dm for", "crypto", "nft", "invest"]
    bio_spam = sum(1 for term in spam_terms if term in bio.lower()) >= 2
    signals.append(BotSignal(
        name="bio_spam",
        triggered=bio_spam,
        weight=3,
        evidence=f"Bio contains spam indicators"
    ))

    # No profile image
    signals.append(BotSignal(
        name="no_profile_image",
        triggered="default_profile_image" in account_data
                   and account_data["default_profile_image"],
        weight=2,
        evidence="Using default profile image"
    ))

    # Posting from automation source
    sources = account_data.get("tweet_sources", [])
    automation_sources = {"IFTTT", "Zapier", "Buffer API", "Hootsuite"}
    auto_posting = bool(set(sources) & automation_sources)
    signals.append(BotSignal(
        name="automation_source",
        triggered=auto_posting,
        weight=3,
        evidence=f"Posts from automation tool: {set(sources) & automation_sources}"
    ))

    return score_account(signals, platform="x", username=account_data.get("username", ""))


# Implement detect_reddit(), detect_tiktok(), detect_instagram(), detect_facebook()
# following the same pattern — one BotSignal per check, then score_account()
```

### Integration with Judge

Add bot score to `PostData`:

```python
@dataclass
class PostData:
    # ... existing fields ...
    bot_score: BotScore | None = None
```

In the judge, append bot context to the prompt:

```python
def build_bot_context(post: PostData) -> str:
    if not post.bot_score or post.bot_score.verdict == BotVerdict.UNKNOWN:
        return ""

    score = post.bot_score
    triggered = [s for s in score.signals if s.triggered]
    signal_summary = "; ".join(s.evidence for s in triggered[:5])

    return f"""

[Account Analysis]
Bot Verdict: {score.verdict.value} (confidence: {score.confidence:.0%})
Score: {score.score} across {len(triggered)} signals
Key signals: {signal_summary}
"""
```

Update the system prompt to include:

```
9. ACCOUNT AUTHENTICITY
   If an [Account Analysis] block is present, factor the bot verdict into your moderation decision.
   A BOT verdict does not change whether content violates policy — violations are violations regardless.
   However, BOT accounts coordinating to spread violating content should be flagged as higher severity
   due to the amplification risk. Note the bot verdict in your explanation when relevant.
```

---

## Using Claude as a Final Arbiter

For borderline SUSPICIOUS accounts, use Claude itself to make the final call. Pass the full signal list and ask for a judgment:

```python
def claude_bot_verdict(account_data: dict, signals: list[BotSignal], platform: str) -> str:
    """
    Use Claude to make a final call on ambiguous SUSPICIOUS accounts.
    Returns: "BOT", "HUMAN", or "UNCERTAIN"
    """
    triggered_signals = [s for s in signals if s.triggered]
    signal_text = "\n".join(f"- {s.name}: {s.evidence}" for s in triggered_signals)

    prompt = f"""
You are analyzing a {platform} account for bot behavior.

Account data:
- Username: {account_data.get('username')}
- Account age: {account_data.get('age_days')} days
- Followers: {account_data.get('followers_count')}
- Following: {account_data.get('following_count')}
- Total posts: {account_data.get('post_count')}
- Bio: {account_data.get('bio', 'empty')}

Triggered bot signals:
{signal_text}

Based on these signals, is this account more likely to be:
1. A BOT or automated account
2. A real HUMAN account
3. UNCERTAIN — not enough information

Respond with exactly one word: BOT, HUMAN, or UNCERTAIN.
Then on the next line, explain your reasoning in one sentence.
"""
    # Call Claude API with this prompt
    # Parse first word of response as verdict
```

This is most useful for accounts in the 3-4 signal range where the score alone isn't conclusive.

---

## Scoring Summary Table

| Platform | Immediate BOT triggers | SUSPICIOUS threshold | BOT threshold |
|---|---|---|---|
| X | tweet<5 + age<30 + following>4900 | score ≥ 5 | score ≥ 10, signals ≥ 4 |
| Reddit | karma-farm + templates + age<7 | score ≥ 5 | score ≥ 10, signals ≥ 4 |
| TikTok | videos=0 + followers>10k | score ≥ 5 | score ≥ 10, signals ≥ 4 |
| Instagram | posts=0 + followers>5k + bio spam | score ≥ 5 | score ≥ 10, signals ≥ 4 |
| Facebook | age<30 + followers>10k + link-only | score ≥ 5 | score ≥ 10, signals ≥ 4 |

---

## What NOT to Build

- **Don't ban on bot score alone** — your pipeline moderates content, not accounts. Flag the score, let humans or the platform decide account-level action.
- **Don't treat HUMAN verdict as clean** — sophisticated bots evade detection. A HUMAN verdict means "no bot signals found", not "definitely human".
- **Don't run bot detection synchronously in the judge** — it adds latency. Run it as a pre-processing step when the post is scraped, store `bot_score` on `PostData`.
- **Don't hard-code thresholds** — platform bot tactics evolve fast. Store thresholds in `config.py` so they can be tuned without code changes.

---

## Implementation Order

```
1.  Create core/bot_detector.py with BotSignal, BotScore, BotVerdict models
2.  Implement score_account() scoring engine
3.  Implement detect_x() with all X signals
4.  Implement detect_reddit() with all Reddit signals
5.  Implement detect_tiktok() with all TikTok signals
6.  Implement detect_instagram() with all Instagram signals
7.  Implement detect_facebook() with all Facebook signals
8.  Add bot_score field to PostData in models.py
9.  Call appropriate detector in each platform adapter after scraping
10. Add build_bot_context() to judge.py
11. Update system prompt with rule 9 (Account Authenticity)
12. Implement claude_bot_verdict() for SUSPICIOUS edge cases
13. Test: known bot account on X → BOT verdict
14. Test: real account with low activity → HUMAN or UNCERTAIN, not BOT
15. Test: coordinated posting pattern across accounts → Critical signal fires
```
