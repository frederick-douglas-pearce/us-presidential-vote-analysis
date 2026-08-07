---
layout: post
title: "It Takes 270, But 270 of What?"
date: 2026-08-05 00:00:00-0800
description: "Electors appointed, votes cast, votes counted: three numbers that are usually identical, and the four elections where they weren't."
categories: ["american-history"]
tags: ["electoral-college", "american-history", "data-quality", "us-presidential-vote-analysis"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/it-takes-270-but-270-of-what-og.png
og_card_source: social/images/2026-08-05-linkedin-it-takes-270-but-270-of-what/og-card.png
featured: false
---

In [December 2000](https://www.archives.gov/electoral-college/2000), one of the District of Columbia's three presidential electors sat down to cast her vote and left it blank. Barbara Lett-Simmons had been appointed, like every elector that year, to formally choose a president. She used the appointment to make a different point instead: a deliberate, public refusal to vote, in protest at DC having a presidential vote but no vote in Congress.

It changed no outcome. George W. Bush had already secured the presidency by a margin her single vote could not touch. But her blank ballot split a number everyone assumes is one thing into the two things it actually is.

Ask how many electoral votes it takes to win the presidency and the answer comes back immediately: 270. Ask what 270 is half of, and the answer gets vaguer. Most people say "538, the total electoral votes" and stop there. That's close, but it isn't what the Constitution says. The Twelfth Amendment sets the threshold at a majority of "the whole number of Electors appointed", not electors who show up, and not votes that get cast. In most years those are the same number, so nobody has reason to notice.

## Appointed, not cast

Every state's electoral allotment, the number of electors it gets to appoint, is fixed well before a single vote is cast. In 2000, those allotments summed to 538. That total didn't move on election day, and it didn't move when the electors met in their state capitals that December. What moved was the second number: how many appointed electors actually cast a vote. Because Lett-Simmons declined, only 537 were recorded. Two real numbers from one election: **538 appointed, 537 cast**.

It isn't the only time they've come apart, and the earlier case has a more ordinary explanation. In [1832](https://www.archives.gov/electoral-college/1832), two of Maryland's ten electors never voted. The [Maryland State Archives](https://msa.maryland.gov/megafile/msa/speccol/sc2900/sc2908/000001/000865/pdf/am865.pdf) records why: Joseph Kent and Gerard N. Cousin "didn't attend the Electoral College meeting because of 'ill health'". Two men were too unwell to travel that December, and the national tally came up short by exactly two: **288 appointed, 286 cast**.

The Twelfth Amendment's threshold reads against the first number, never the second. A majority of 538 appointed electors is **270**. A majority of 537 cast votes, had that been the basis, would have required only **269**. One fewer, because the total it's measured against is smaller. Bush's 271 cleared both, so nothing in 2000 turned on which applied. At 269 everything would have: a majority of the votes cast, short of a majority of the electors appointed, and the House choosing the president.

The Constitution doesn't offer that option, so [this project](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis) keeps the two totals apart: an allotment per state, recorded once, and a vote count per candidate, checked against it. The two sit on opposite sides of the same fraction. Appointed sets the denominator, the bar a candidate has to clear. Cast fills the numerator, what each candidate received. Merge them into one column and the bar drops with the abstentions: the fewer electors who vote, the less it takes to win. Measuring against electors appointed is what fixes the bar in place.

## Then there is a third number

Two numbers would be manageable, but [1872](https://www.archives.gov/electoral-college/1872) demonstrates a third.

Horace Greeley, the Democratic and Liberal Republican nominee, lost the popular vote in November and then died on the 29th of that month, before the electors met. His pledged electors scattered. They cast votes for Thomas A. Hendricks, for Greeley's own running mate B. Gratz Brown, for Charles J. Jenkins, for David Davis. Three electors in Georgia voted for Greeley anyway. By resolution of the House, those three votes were not counted.

Count the election three ways and get three answers. The states appointed **366** electors. Arkansas's six and Louisiana's eight never entered the count at all, so the Archives table totals **352**. Subtract the three votes cast for a dead man and refused by the House, and **349** were counted for president.

Three totals, three different majorities: 184, or 177, or 175. Grant took 286 and cleared all three, which is the only reason nobody had to decide which was correct.

One of those numbers is hiding more than the others. The Archives says only that Arkansas and Louisiana were "unable to certify their election results", an administrative phrase for a collapse of legitimate government in both. Louisiana came out of 1872 with two rival governments, each certifying its own slate of electors. Congress received both slates and rejected both. Arkansas's governorship was disputed the same way.

Neither quarrel stayed on paper. Louisiana's produced the Colfax massacre in 1873 and an armed seizure of New Orleans the year after. Arkansas's led to the Brooks–Baxter War of 1874, fought with militia in Little Rock. The violence didn't follow from the uncounted votes. Both followed from the same problem: two governments in each state, each claiming to be the real one, with no clear authority.

## When the record itself won't say

For [1868](https://www.archives.gov/electoral-college/1868), the situation is worse: the official record declines to pick a number.

Georgia again, for an unrelated reason four years earlier: its nine electoral votes were contested. In the Archives' own words, "the Senate and the House of Representatives could not agree whether to accept – and count – them or not." So the table ends with **two totals rows**: 285 excluding Georgia, 294 including it. Both are printed. Neither is marked correct. A majority is 143 under one and 148 under the other.

The dispute was over whether Georgia was yet a state in good standing, and Congress saw it coming. Two days before the count, it resolved that Georgia's votes would be announced both ways.

On February 10, 1869, Benjamin Butler [objected on four grounds](https://www.govinfo.gov/content/pkg/GPO-HPREC-HINDS-V3/html/GPO-HPREC-HINDS-V3-10.htm): that Georgia's electors had not voted on the day federal law required, that the state had not been admitted to representation in Congress, that it had not satisfied the Reconstruction Acts, and that its November election had not been "a free, just, equal, and fair election." The House voted against counting the votes, 41 to 150. The Senate ruled the objection out of order.

Grant had 214 and won under either total, which is again why it was allowed to stand unresolved. That 294 counts only the states that had electors to appoint. Not yet readmitted to the Union, Mississippi, Texas, and Virginia appointed none, so they don't appear in the table at all.

Here is where a historical curiosity turns into a schema problem. A prose footnote can hold two irreconcilable totals. A column holds one number. Something has to decide whether 1868's denominator is 285 or 294, and picking one gives the appearance of taking a side in a dispute Congress itself never settled.

But those two totals disagree about the wrong thing. Georgia's nine electors were **appointed**, and nobody ever disputed that. The Twelfth Amendment's denominator asks only how many electors were appointed. What Congress deadlocked over was whether their votes should be **counted**, which is a different question, about a different number. So the denominator is 294, and no side has been taken, because the side-taking was never in the denominator.

That leaves the real dispute to be recorded rather than resolved. In [the model these two years get](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/57), every vote row carries a status: counted, not counted, or disputed. Georgia's nine in 1868 are marked **disputed**, with the Archives' own sentence attached as the reason. Three of Georgia's eleven in 1872 are marked **not counted**, since the House said no, while the other eight are counted: status belongs to a vote, not to a state. Arkansas's six and Louisiana's eight are not counted either.

The gap between those two labels is the whole point. *Not counted* means Congress decided no. *Disputed* means Congress never reached a decision. A single "contested" flag covering both would be quietly asserting that 1868 was settled.

So ask this record for 1868's total and it asks back whether you want the disputed votes in it. That isn't evasion. It's the only honest answer to a question the Senate and the House never agreed on.

## The one time it happened

The House has actually had to choose a president, once. In [1824](https://www.archives.gov/electoral-college/1824), four candidates split 261 electoral votes and nobody reached 131. Jackson led with 99, **thirty-two short**. Every one of those 261 was appointed, cast, and counted: nothing missing, nothing rejected. [The previous post](https://frederick-douglas-pearce.github.io/blog/2026/presidential-elections-are-messy/) was about what a record does when something is missing. This is the case where nothing is, and there still isn't a majority. A field can fail to produce one without a single number going astray.

The House chose Adams, who had finished second. That's the part the record can't flatten. Jackson led the Electoral College, Adams took the presidency, and in every other election on file those two describe the same person, which makes it tempting to store one column and call it "the winner."

So the record keeps two: whether the electoral leader cleared a majority outright, and who actually took office. For 1824 the first reads false and the second names Adams. Everywhere else they agree. A record that only tells the truth when the two line up isn't recording the second fact at all.

None of this explains where 538 comes from: why the House sits at 435 seats, why the Senate contributes 100, why the District of Columbia counts for three electors instead of zero. It explains only what a majority of that number means once you have it. Appointed, not cast, not counted, and unmoved by who does or doesn't use the vote they were given.

---

_Drafted with Claude Code. The ideas, claims, and any errors are mine._
