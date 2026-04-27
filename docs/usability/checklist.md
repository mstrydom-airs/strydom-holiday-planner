# Usability Checklist

Run this checklist for every UI change. Record results in a PR comment and link
back to the relevant `UC-` need.

## Task completion

- [ ] A first-time user can complete the primary task on each page within 60s.
- [ ] All buttons and links communicate their result before being clicked.
- [ ] Forms keep entered data when validation fails.
- [ ] (Home) With saved trips, month headings and the right-hand month rail
      (if visible) make it clear which month is in view; rail buttons scroll to
      the matching section (`UC-002`).

## Error recovery

- [ ] Every error message tells the user what to do next.
- [ ] Network/server errors surface gracefully (no raw stack traces).
- [ ] The browser back button works on every page.

## Accessibility (WCAG 2.1 AA)

- [ ] All interactive elements are reachable via keyboard.
- [ ] Visible focus indicator on every interactive element.
- [ ] Form fields have programmatically associated labels.
- [ ] Colour contrast ratio ≥ 4.5:1 for body text, ≥ 3:1 for large text.
- [ ] axe-core scan reports zero serious or critical issues.

## Mobile / responsive

- [ ] Layout works at 320 px wide.
- [ ] Tap targets are ≥ 44×44 px.
- [ ] No horizontal scrolling on portrait phones.

## Performance

- [ ] Lighthouse Performance ≥ 90 on a throttled 3G profile.
- [ ] Lighthouse Accessibility, Best Practices, SEO ≥ 90.
