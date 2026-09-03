---
layout: post
title: "How Did We Get to 538 Electors Anyway?"
date: 2026-09-03 00:00:00-0800
description: "The House has been 435 seats since 1913, and Congress made that permanent in 1929. Add 100 senators and 3 for Washington DC, and that is where 538 comes from."
categories: ["us-presidential-vote"]
tags: ["electoral-college", "american-history", "data-quality", "us-presidential-vote-analysis"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/how-did-we-get-to-538-electors-og.png
og_card_source: social/images/2026-09-03-linkedin-how-did-we-get-to-538-electors/og-card.png
featured: false
---

Everyone who follows US presidential elections can recite that it takes 270 electoral votes to win. Ask where 538 comes from, and the answer is often vague: "that's just how many votes there are." True, but why? 538 is the sum of the 435 members of the House of Representatives, 100 senators, and three votes assigned to the District of Columbia. It has been 538 since 1964. Before that it was 537, for exactly one election, and 531 for the eight elections before that. The House is most of the count, and the story. It happened to have 435 members in 1929, and that number was made permanent right after the one decade in American history when Congress skipped the reapportionment the census is supposed to trigger.

## An existing number, made permanent

The common misconception is that Congress fixed the House at 435 members in 1929. The [Permanent Apportionment Act of 1929](https://www.govinfo.gov/content/pkg/STATUTE-46/pdf/STATUTE-46-Pg21.pdf) never says that: the number 435 doesn't appear anywhere in its text. What it does instead is make apportionment self-executing. After each census the seats are redistributed among the states automatically, unless Congress passes an apportionment of its own. The number being redistributed is whatever the House already has, "the then existing number of Representatives." The Act didn't write a ceiling, it made reapportionment the default.

In 1929, the House count was 435. The [1911 Act](https://www.govinfo.gov/content/pkg/STATUTE-37/pdf/STATUTE-37-Pg13.pdf), the one that actually wrote a number down, set the House at 433 as of March 1913, with a seat each for Arizona and New Mexico if they were admitted first. Both were, in 1912, so the chamber opened the 63rd Congress at 435, never having sat at 433. Each admitted state brought two senators as well, and a state's electors are its House seats plus its senators, so the pair added six electoral votes, not two. That brought the national total to 531: 435 House seats plus 96 senators, for 48 states. The last presidential election before the Permanent Apportionment Act, in 1928, already ran at 531, the same total [this project's own record](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis) shows for every election from 1928 through 1956.

The House's own [historian](https://history.house.gov/Historical-Highlights/1901-1950/The-Permanent-Apportionment-Act-of-1929/) gives two different accounts of the 1929 Act on a single page. The opening sentence says Congress passed it "fixing the number of Representatives at 435," which has the Act choosing the number. A later paragraph says it "capped House Membership at the level established after the 1910 Census," which has it inheriting one. The first is the loose version, and finding it in the opening sentence of the House's own account is a fair measure of how universal the misconception has become. The statute is the citation here, not any page that describes it.

## The decade Congress skipped

Reapportionment is supposed to happen every ten years. Each state's share of the House, and with it its share of the Electoral College, is redrawn against the new census. After the 1920 census, Congress passed no new apportionment at all, the only decade in American history with that gap.

A flat national total doesn't prove that on its own. The total sat at 531 for every election from 1912 through 1932, but the House had been fixed at 435 since 1913, and reapportionment only moves seats between states. Whether Congress redrew the map or not, the national sum reads the same. The signature of a skipped reapportionment shows up one level down, in which states' allotments actually moved:

| election | states whose allotment changed   | national total |
| -------- | -------------------------------- | -------------- |
| 1904     | 20                               | 476            |
| 1908     | 0 (plus Oklahoma)                | 483            |
| 1912     | 25 (plus Arizona and New Mexico) | 531            |
| 1916     | 0                                | 531            |
| 1920     | 0                                | 531            |
| 1924     | 0                                | 531            |
| 1928     | 0                                | 531            |
| 1932     | 32                               | 531            |
| 1936     | 0                                | 531            |
| 1940     | 0                                | 531            |
| 1944     | 16                               | 531            |

Reapportionment happens once a decade, so zeros are ordinary. 1908, and again 1936 and 1940, are what a normal decade looks like: the map moves at the first election after a census and holds until the next one. Four zeros in a row is not normal. The allotment set drawn up for the 1912 election stood unchanged through 1928, four consecutive elections and sixteen years, with the 1920 census sitting in the middle of that stretch and changing nothing. Every other census in the surrounding half-century moved 16 to 32 states at the next election. The map that elected a president in 1924, and again in 1928, was the map drawn after the 1910 census.

That failure is visible in this project's own record, with no appeal to anything outside it. Why Congress let it happen is a different question, and one the record doesn't answer.

## What the House floor sounded like

The census that triggered the crisis had also just found something new: 1920 was the first time the count showed more Americans living in cities than in the countryside. The stakes were real. Whether that shift is what stopped reapportionment is contested.

The House's own [historian](https://history.house.gov/Historical-Highlights/1901-1950/The-Permanent-Apportionment-Act-of-1929/) puts it this way: "A battle erupted between rural and urban factions, causing the House (for the only time in its history) to fail to reapportion itself following the 1920 Census." The [Census Bureau](https://www.census.gov/about/history/historical-censuses-and-surveys/census-programs-surveys/decennial-census/legislation-1890-present.html) describes a Congress "dominated by rural politicians who stood to lose clout in a quickly urbanizing nation." It's also the title thesis of the standard scholarly account, Charles W. Eagles' _Democracy Delayed: Congressional Reapportionment and Urban-Rural Conflict in the 1920s_ (1990).

The one study that actually modeled how members voted found something different. [Napolio and Jenkins](https://www.cambridge.org/core/journals/journal-of-policy-history/article/conflict-over-congressional-reapportionment-the-deadlock-of-the-1920s/EF7DC3467A2812EEA2490EF2239DC499), writing in the _Journal of Policy History_ in 2023, ran the actual roll calls and reported, verbatim: "We find no evidence that members from rural areas opposed reapportionment independent of other factors, such as party or ideology." What predicted a member's vote was whether their own state was slated to lose seats, plus party.

Two things temper that finding rather than flip it. It's a null result, not proof that rural feeling played no role. The claim is narrower than it looks: no rural effect _independent of_ party and ideology. If rural sentiment ran through party in the first place, a model that already holds party constant would not see it. The study's seat-loss variable is itself coded from Eagles, so this is a regression on the monograph's own data, not an independent dataset overturning it. Both were probably true at once. The House floor sounded emphatically urban and rural, and the votes tracked seat exposure and party. Members also argued, separately, that the House had simply grown too large, too expensive to run, and too short on space in its own chamber, a complaint that had nothing to do with cities or farms.

## A century-old habit, tried once more

For more than a century after 1790, Congress generally defused this kind of dispute by making the House bigger instead of trading seats between states. The [Congressional Research Service](https://www.congress.gov/crs_external_products/IN/PDF/IN11547/IN11547.4.pdf) states the motive plainly: in the eighteenth and nineteenth centuries, Congress "generally increased the size of the House with each apportionment so no state would lose seats." The chamber grew from 105 seats in 1790 to 433 by 1910, decade after decade, almost every time a census came due.

The practice wasn't ironclad. In 1842 the House shrank, 242 seats down to 223, the only decrease in the chamber's history. Growing the chamber never guaranteed anyone kept a seat. The [Census Bureau](https://www.census.gov/about/history/historical-censuses-and-surveys/census-programs-surveys/decennial-census/legislation-1790-1830.html) notes that "the 1820 reapportionment was the first time states lost House representation in absolute terms," in a year the House grew from 181 to 213 seats. The loss was absolute, not proportional. Some states sent fewer members than before. Enlargement was the tool Congress reached for, and it usually worked. It was never a promise.

In 1921, Representative Isaac Siegel of New York proposed enlarging the House to 483 seats, the size at which, on the 1920 numbers, no state would have lost a single seat. It failed, against resistance that included members of his own party. The [American Academy of Arts and Sciences](https://www.amacad.org/ourcommonpurpose/enlarging-the-house/section/2) spells out the stakes: "ten rural states were slated to lose a combined eleven seats, which would have gone instead to eight urbanizing states." A century-long habit, tried one final time, and refused, in a single bill. Had it passed, the frozen number would have been 483, and it would take 294 electoral votes to win today.

## Two moves since the freeze

With growth off the table and reapportionment automatic, the total number of electoral votes has moved exactly twice since 1929, and neither move had anything to do with population.

In 1960 the total rose to 537. Alaska and Hawaii had joined the union the year before, bringing four senators between them, and each also got a temporary House seat on top of the existing 435 while the chamber waited for its next reapportionment. Six votes, two of them temporary. The [Alaska Statehood Act](https://www.govinfo.gov/content/pkg/STATUTE-72/pdf/STATUTE-72-Pg339.pdf) is explicit that the extra seat lasted only "until the taking effect of the next reapportionment," and that it would not "affect the basis of apportionment established by the Act of November 15, 1941." When the apportionment that followed the 1960 census took effect, the House went back to 435. The Electoral College total did not follow it down, and the reason is a coincidence of timing rather than a rule: the House gave back its two temporary seats in the same stretch that the Twenty-Third Amendment gave the District of Columbia three votes, first cast in 1964. Two off, three on, so the total moved up by one, and it has held at 538 for the sixteen elections since.

Apart from those two, every change to the electoral map since 1932 has been reapportionment: seats, and electoral votes, moving from one state to another as the House holds its size. The total hasn't grown with the country.

Those three DC votes have their own story, and [the previous post](https://frederick-douglas-pearce.github.io/blog/2026/it-takes-270-but-270-of-what/) told it in full. First cast in 1964. In 2000, one of them was handed in blank, in protest at DC still having no vote in Congress.

What the record doesn't yet answer is how unequal a single electoral vote has become since the total stopped moving. Persons per electoral vote, by state, by decade, is a number this project's own data could eventually compute back across most of two centuries. It needs a population dimension the project doesn't have yet.

That arithmetic, 435 plus 100 plus 3, fixes how many electors there are. It names none of them, and it can't: the Constitution bars sitting senators and representatives from serving as electors. So 538 counts a different several hundred people entirely, appointed state by state, each of whom has to show up in December and choose. The 1929 freeze settled how many of them there would be. It said nothing about what they would do once they got there, and the record of that turns out to be more surprising than the arithmetic.

---

_Drafted with Claude Code. The ideas, claims, and any errors are mine._
