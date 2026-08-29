---
name: network-analysis
description: >-
  Analyse device interface, alarm and health output. Load whenever the user asks
  why a link is down, what an alarm means, or for a health summary of a device.
version: 1.0.0
---

# Network Analysis

**Contents:** [When to use](#when-to-use) · [Procedure](#procedure) · [Escalation](#escalation)

## When to use

The user asks about link state, alarms, counters or overall device health.

## Procedure

1. Identify the device and family from the user's request.
2. Read live state before proposing any change.
3. Summarise findings with the evidence you used.

## Escalation

Never propose a configuration change without showing the diff first.
