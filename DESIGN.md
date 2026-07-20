---
name: trailkeep
description: A calm, local-first viewer for durable AI coding history.
colors:
  spine: "#0F2A28"
  spine-raised: "#143836"
  paper: "#FAFAF6"
  panel: "#FFFFFF"
  ink: "#1A2421"
  ink-muted: "#5A655F"
  line: "#E4E7E3"
  line-strong: "#CBD2CD"
  intent: "#C2553B"
  assistant: "#2F6F69"
  tool: "#8A7A52"
  tool-surface: "#F2EFE7"
  code-surface: "#102220"
  code-text: "#D7E4DF"
  selection: "#FBE9CF"
  completed: "#9AA39E"
  source-claude-code: "#2F8F82"
  source-codex: "#8B7FD4"
  source-cowork: "#D49A52"
  source-opencode: "#5B9BD8"
  source-cursor: "#D87093"
typography:
  display:
    fontFamily: 'ui-serif, "Iowan Old Style", "Palatino Linotype", Georgia, serif'
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.2
  headline:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", sans-serif'
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.25
  title:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", sans-serif'
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.22
  body:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", sans-serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.62
  metadata:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", sans-serif'
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.4
  control:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", sans-serif'
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.2
  label:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", sans-serif'
    fontSize: "10px"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "0.16em"
  mono:
    fontFamily: 'ui-monospace, "SF Mono", Menlo, Monaco, "Cascadia Code", monospace'
    fontSize: "12.8px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: "4px"
  sm: "6px"
  control: "7px"
  md: "8px"
  tool: "9px"
  lg: "10px"
  notice: "12px"
  card: "14px"
  dialog: "18px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "6px"
  md: "8px"
  control: "10px"
  lg: "12px"
  xl: "16px"
  panel: "20px"
  section: "24px"
  reader: "38px"
components:
  button-primary:
    backgroundColor: "{colors.intent}"
    textColor: "{colors.panel}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "8px 13px"
  button-ghost:
    backgroundColor: "{colors.spine}"
    textColor: "{colors.code-text}"
    typography: "{typography.control}"
    rounded: "{rounded.md}"
    padding: "8px 13px"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.metadata}"
    rounded: "{rounded.control}"
    padding: "5px 10px"
  search-field:
    backgroundColor: "{colors.code-surface}"
    textColor: "{colors.code-text}"
    typography: "{typography.metadata}"
    rounded: "{rounded.md}"
    padding: "7px 11px 7px 30px"
    width: "240px"
  filter-chip:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.metadata}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  project-card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "15px 17px"
  analytics-card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "18px 20px"
  subagent-disclosure:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.metadata}"
    rounded: "{rounded.lg}"
    padding: "9px 11px"
    height: "44px"
---

# Design System: trailkeep

## Overview

**Creative North Star: "The Local Field Notebook"**

trailkeep should feel like a well-kept technical notebook that happens to be interactive: private, cumulative, quiet, and dependable. The dark teal spine anchors navigation while the warm paper reader preserves long-form comfort. Clay appears only where the interface asks the user to act or marks their own voice.

The system serves scanning first and reading second. Dense metadata stays compact, hierarchy is predictable, and detail opens in place. It rejects generic admin-dashboard density, cloud-product theater, and decorative AI chrome. Every surface must reinforce that the archive is local, stable, and under the user's control.

**Key Characteristics:**

- A dark structural spine paired with a warm, low-glare reading field.
- Restrained clay emphasis for primary intent and the user's own turns.
- Compact system typography for controls, metadata, and navigation.
- A serif reading accent for document titles and the trailkeep wordmark.
- Borders and tonal layers before shadows; motion only explains state.
- Source colors used as identity metadata, never as page decoration.

## Colors

The palette combines archival paper, deep privacy teal, and a small clay accent. Semantic and source colors remain local to the data they explain.

### Primary

- **Intent Clay** (`intent`): primary actions, current control state, focus rings, and user-turn identity. Its rarity makes intent immediately legible.

### Secondary

- **Privacy Spine** (`spine`): top bar, navigation rail, and trusted structural chrome.
- **Raised Spine** (`spine-raised`): secondary navigation layers and subtle dark-surface separation.
- **Assistant Teal** (`assistant`): assistant-turn identity, completion checks, and calm interactive emphasis.

### Tertiary

- **Tool Ochre** (`tool`): tool-call identity and evidence-related metadata.
- **Source Set** (`source-claude-code`, `source-codex`, `source-cowork`, `source-opencode`, `source-cursor`): compact source badges only. Each source keeps one stable color in every view.

### Neutral

- **Archive Paper** (`paper`): the main reading field and quiet nested surfaces.
- **Clean Panel** (`panel`): cards, controls, and foreground containers.
- **Soft Black Ink** (`ink`): primary text and high-confidence values.
- **Muted Ink** (`ink-muted`): supporting copy, labels, and metadata.
- **Quiet Line** (`line`) and **Strong Line** (`line-strong`): structural boundaries and interactive affordances.
- **Tool Paper** (`tool-surface`): evidence blocks and quiet hover surfaces.
- **Code Night** (`code-surface`) and **Code Mist** (`code-text`): local code and dark-field controls.
- **Selection Parchment** (`selection`) and **Completed Gray** (`completed`): transient selection and reviewed-state cues.

### Named Rules

**The Observable Privacy Rule.** Dark structural surfaces communicate local custody, but privacy claims must still be stated in clear text where they matter.

**The Clay Intent Rule.** Intent Clay is reserved for primary action, focus, active selection, and the user's voice. It is never decorative.

**The Source Color Rule.** Source colors label provenance in compact badges and charts. They never tint whole cards or compete with reading content.

## Typography

**Display Font:** the native serif stack with Iowan Old Style and Palatino fallbacks.

**Body Font:** the native system sans stack.

**Label/Mono Font:** the native monospace stack led by SF Mono.

**Character:** Native font stacks keep the standalone viewer fast, offline, and familiar on macOS and Linux. Serif is a reading accent, not application chrome; sans and mono carry the operational interface.

### Hierarchy

- **Display** (600, 26px, 1.2): conversation titles and the strongest document-level headings.
- **Headline** (700, 20px, 1.25): view titles and primary section headings.
- **Title** (700, 15px, 1.22): project names, card titles, and high-confidence row labels.
- **Body** (400, 15px, 1.62): conversation reading. Prose stays inside the 840px reader and should not exceed roughly 75 characters per line.
- **Metadata** (500, 12px, 1.4): dates, counts, descriptions, and secondary actions.
- **Control** (600, 12.5px, 1.2): buttons and high-priority compact controls.
- **Label** (700, 10px, 0.16em, uppercase): navigation sections and terse categories only.
- **Mono** (400, 12.8px, 1.5): code, git facts, tool names, and machine identifiers.

### Named Rules

**The Reading Accent Rule.** Serif belongs to the wordmark and document reading hierarchy. Buttons, labels, badges, and data stay in the system sans.

**The Quiet Metadata Rule.** Metadata earns hierarchy through size, weight, and muted color. Never shrink operational text below 9.5px.

## Elevation

trailkeep is flat by default. Paper, panels, one-pixel borders, and tonal changes establish hierarchy. Shadows appear only when a surface genuinely lifts above another surface or responds to hover.

### Shadow Vocabulary

- **Card Hover** (`0 4px 14px rgba(0,0,0,.06)`): project cards only while interactive hover is active.
- **Notice Lift** (`0 2px 8px rgba(112,80,28,.06)`): low, warm lift for review notices.
- **Tooltip Lift** (`0 6px 20px rgba(0,0,0,.3)`): compact overlays that must clear dense data.
- **Drawer Lift** (`-16px 0 40px rgba(0,0,0,.18)`): side panels that sit above the reader.
- **Dialog Lift** (`0 24px 70px rgba(0,0,0,.45)`): the blocking demo explanation only.

### Named Rules

**The Flat-at-Rest Rule.** Static cards do not float. If a shadow is visible without hover, disclosure, or modal state, remove it.

**The Structural Border Rule.** Use full one-pixel boundaries and tonal layers. Colored side stripes and ornamental separators are prohibited.

## Components

Components are compact, familiar, and stateful. Controls reuse the same radii, border vocabulary, and 120ms feedback rhythm across every view.

### Buttons

- **Shape:** gently rounded controls (7px to 8px radius) with compact padding.
- **Primary:** Intent Clay with clean light text. Use one obvious primary action per local context.
- **Hover / Focus:** hover changes tone or brightness; keyboard focus uses a 2px Intent Clay outline with 2px offset.
- **Secondary / Ghost:** light secondary buttons use panel surfaces and strong lines. Dark ghost buttons use a transparent Privacy Spine surface with a teal-gray border.
- **Disabled:** reduce opacity while preserving the control's shape and label. Disabled hover never changes the surface.

### Chips

- **Style:** pill geometry, compact metadata type, quiet lines, and panel backgrounds.
- **State:** selected chips invert to Privacy Spine or their source color. State is also communicated by text and contrast, never color alone.

### Cards / Containers

- **Corner Style:** calm, continuous corners (10px to 14px radius).
- **Background:** Clean Panel over Archive Paper.
- **Shadow Strategy:** flat at rest; project cards gain only Card Hover elevation.
- **Border:** one-pixel Quiet Line at rest, Strong Line on hover.
- **Internal Padding:** 14px to 20px according to information density.

### Inputs / Fields

- **Style:** dark search fields sit inside the spine with a 1px teal-gray stroke, 8px radius, and visible search icon. Text inputs on paper reuse panel and line tokens.
- **Focus:** the global Intent Clay focus ring remains visible without moving layout.
- **Error / Disabled:** errors use explicit inline copy and a semantic border or text cue. Disabled fields preserve readable contrast.

### Navigation

- The desktop shell uses a 340px dark sidebar and a flexible reader. Navigation rows are compact, left-aligned, and visibly respond to hover and active state.
- At 860px and below, the sidebar becomes an app-owned bottom sheet opened by the menu button. Content becomes one column and practical touch targets remain at least 44px tall.
- Sticky headers use translucent Archive Paper only to preserve context during scrolling; blur is functional, never decorative.

### Conversation Turn

- Turns use a stable label, checkbox, preview, and disclosure affordance. Expanded content stays in the timeline instead of opening a modal.
- User, assistant, and tool identity use text plus stable color. Tool output moves onto Tool Paper and code moves onto Code Night.
- Related subagents nest inside the parent timeline with explicit status, depth, and a minimum 44px disclosure target.

## Do's and Don'ts

### Do:

- **Do** keep all fonts, icons, scripts, and visual assets local or inline so the viewer remains zero-network.
- **Do** preserve the 340px desktop sidebar, 840px reading measure, and 860px structural breakpoint unless a measured usability problem requires change.
- **Do** expose density progressively through inline disclosure, sticky context, filters, and project drill-down.
- **Do** reuse Intent Clay for primary action and focus, Privacy Spine for structure, and source colors for provenance only.
- **Do** keep every interactive row visibly responsive on desktop and practically tappable on mobile.
- **Do** add every user-facing string to both English and Spanish dictionaries.

### Don't:

- **Don't** create cloud-first builder profiles or upload raw or derived activity. Privacy is the product.
- **Don't** add telemetry-driven dashboards or interfaces that hide what data leaves the machine.
- **Don't** turn the archive into a dense, generic admin dashboard that flattens conversations into disconnected metrics.
- **Don't** add decorative AI-product chrome, novelty interactions, or visual effects that compete with reading.
- **Don't** use browser-native product controls or inconsistent local lookalikes for dropdowns, disclosures, toasts, confirmations, or tooltips.
- **Don't** use external fonts, CDN assets, gradients, glassmorphism, gradient text, or ornamental colored side stripes.
- **Don't** make static cards float. A persistent shadow is allowed only for a real overlay, drawer, or blocking dialog.
- **Don't** use source colors as large background fields or rely on color alone to communicate state.
