# Exemplar: STAT 241 weekly R/Quarto problem set (shape only)

Derived from the structure of seven completed problem sets built on the course's Quarto template. The dataset, variables, numbers and problem numbers below are invented. Nothing here is a real answer.

This is the **source** file. What gets submitted is the PDF the student renders from it in their own Quarto and R install. This repo cannot render it or run the R.

---

## Header (the template's, two fields changed per week)

```yaml
---
title: "Homework [N]"                       # change every week
author: "[Student Name]"
date: '`r format(Sys.Date(), "%B %d, %Y")`'   # prints the render date
# format: html
format: pdf
output-file: "Homework [N].pdf"              # the template's fixed name overwrites earlier weeks; set it per homework
fig-height: 2.5
fig-width: 5.5
fig-align: center
fig-cap-location: bottom
geometry:
   - top = 1in
   - bottom = 1in
   - left = 1in
   - right = 1in
   - heightrounded
fontsize: 12pt
editor: visual
---
```

## Setup chunk (hidden from the PDF)

````
```{r}
#| label: load-packages
#| include: false

library(mosaic)
library(tidyverse)
# ...plus the course's fixed list of textbook-data packages
```
````

## One heading and one chunk per problem

````
## Problem [N.NN]

```{r}
# [dataset]: [one line on what each variable measures, with units]
fit.[short] = lm([response] ~ [predictor], data = [dataset])
summary(fit.[short])

gf_point([response] ~ [predictor], data = [dataset]) |>
  gf_lm() +
  labs(x = "[predictor] ([units])", y = "[response] ([units])")

gf_point(resid(fit.[short]) ~ [predictor], data = [dataset]) +
  labs(y = "residual ([units])")

## a) Fitted line: [response] = [b0] + [b1]([predictor]).
##    Slope [b1] ± [SE] [units] per [unit of predictor].
## b) Residuals show [no pattern / a funnel / curvature], so [conclusion].
## c) [Mean response at x = value, so a CONFIDENCE interval | one new
##    individual at x = value, so a PREDICTION interval]:
##    [lower] to [upper] [units].
```
````

Keep every code and comment line short. The PDF does not wrap them, and a long answer comment gets cut off at the right margin.

## Hypothesis-test problems use the same shape

````
## Problem [N.NN]

```{r}
## H0: mu = [value] [units]    Ha: mu [> | < | !=] [value] [units]
## [dataset]$[variable] is in [units]; [value] is in the same units.
t.test([dataset]$[variable], mu = [value], alternative = "[greater|less|two.sided]")
## t = [t], df = [df], p = [p]. At the [level] level, [reject | fail to
## reject] H0: [one-sentence conclusion in context].
```
````

## Before calling it done

- The PDF was rendered from this week's source, is named for this week, and shows this week's title.
- Every problem heading and part label is present, in order.
- No line in the PDF is cut off at the margin.
