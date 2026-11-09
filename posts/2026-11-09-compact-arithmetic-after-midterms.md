---
layout: post
title: "222 Plus Five States: The Compact's Arithmetic, as of November 2026"
date: 2026-11-09 00:00:00-0800
description: "After the 2026 midterms, five states without the National Popular Vote Interstate Compact have new Democratic trifectas. A snapshot of the arithmetic as of November 2026: what they would add, what is necessary, and what a trifecta has not been enough to do."
categories: ["us-presidential-vote"]
tags: ["electoral-college", "us-presidential-vote-analysis"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/compact-arithmetic-after-midterms-og.png
og_card_source: social/images/2026-11-08-linkedin-compact-arithmetic-after-midterms/og-card.png
humanizer_pass: none
featured: false
---

After the 2026 US midterms, it's looking like six states will have new Democratic trifectas, with Democrats holding the governorship and both legislative chambers, according to the [National Conference of State Legislatures](https://www.ncsl.org/state-legislatures-news/details/2026-state-legislative-elections-the-results-and-what-they-mean)' unofficial count. Within days of the vote, outlets including [USA TODAY](https://www.usatoday.com/story/news/politics/elections/2026/11/06/democrats-elect-president-popular-vote-electoral-college/92631637007/) and [The New Republic](https://newrepublic.com/post/217594/democrats-seats-nationwide-end-electoral-college) were asking what those trifectas mean for how the US elects its president. This is a snapshot as of November 2026. Results are unofficial until certified, and the figures below are as of November 8 for the compact's tally and November 6 for NCSL's count.

The reason is the National Popular Vote Interstate Compact (NPVIC). States that join agree to appoint their electors for whoever wins the national popular vote, but only once enough states have joined to hold 270 electoral votes, a majority of the Electoral College. Minnesota is one of the six trifecta states, but it's already a member. The other five are not.

## The arithmetic

As of November 8, 2026, the compact's [status page](https://www.nationalpopularvote.com/state-status) shows member jurisdictions holding 222 electoral votes, 48 short of 270. Using the 2024 allotments, the five non-member states hold:

- Pennsylvania: 19
- Michigan: 15
- Arizona: 11
- Wisconsin: 10
- Nevada: 6

That's 61. All five together would bring the compact to 283.

Two things follow from the sums. Pennsylvania and Michigan are each necessary: without Pennsylvania the total tops out at 264, without Michigan at 268. With both, any two of Arizona, Wisconsin and Nevada are enough, and any one alone is not.

Not every list includes Arizona. USA TODAY names Michigan, Minnesota, Nevada, Pennsylvania and Wisconsin. NCSL also counts Arizona, and so does The New Republic's tally. Without Arizona, the four non-members reach 272. With it, 283.

## A trifecta is not an enactment

In two of these states, a trifecta has not been enough on its own. Nevada had one in 2019, when its legislature passed a compact bill, AB 186, and Governor Steve Sisolak [vetoed it](https://archive.leg.state.nv.us/Session/80th2019/Reports/VetoMessages/AB186_80th_VetoMessage.pdf) on May 30. Michigan had a Democratic trifecta in 2023 and 2024, and its compact bill, HB 4156, [passed a House committee and went no further](https://www.nationalpopularvote.com/state-status).

## Open questions

A legal question sits behind all of it: whether the Compact Clause requires Congress to consent to an interstate agreement like this one. The [Congressional Research Service](https://crsreports.congress.gov/product/pdf/R/R43823) has examined it and left it unresolved. The New Republic notes that the filibuster would matter if consent is required. And USA TODAY reports the compact could take effect as early as 2028. That is its reporting, not a forecast of mine.

## The allotments are a snapshot too

The 2024 allotments are in force through the 2028 election. After the 2030 census, House seats, and with them electoral votes, are reapportioned, and the 270 math is redone on the new numbers. I make no projection of what they will be.

The current allotments are public, free and need no key. [`GET /v1/elections/2024?state=PA`](https://api.us-presidential-election-center.org/v1/elections/2024?state=PA) returns Pennsylvania's `state_electoral_votes`, 19. Swap in MI, AZ, WI or NV to check the rest.

I'm not arguing for or against the compact. The record behind this is the one I described in [222 Votes Away, and a Record Few Can Get End to End](https://frederick-douglas-pearce.github.io/blog/2026/222-votes-away/).

---

_Drafted with Claude Code. The ideas, claims, and any errors are mine._
