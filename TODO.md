# TODO - Active Work Tracker

> Track current progress on the [ROADMAP](./gesture-slides-roadmap.md). Move items here when starting work, check off when done.

---

## In Progress

*No active tasks. Pick from Ready to Start below.*

---

## Ready to Start

### Epic 2: User Customization (Recommended Next)

#### Story 2.1: Enable Per-App Key Bindings
**Priority:** High | **Effort:** Low
- [ ] Uncomment default app bindings in `config.py`
- [ ] Add more app presets (PowerPoint, Keynote)
- [ ] Add tests for per-app binding matching
- [ ] Document how to add custom bindings

---

### Epic 1: Core Gesture System

#### Story 1.1: Add First/Last Slide Gestures
**Priority:** High | **Effort:** Medium
- [ ] Design gesture mappings
- [ ] Add config keys for new gestures
- [ ] Implement first slide detection
- [ ] Implement last slide detection
- [ ] Add tests
- [ ] Update README

---

### Epic 3: Dashboard & Remote Control

#### Story 3.1: Remote Slide Control
**Priority:** High | **Effort:** Medium
- [ ] Add control buttons to dashboard
- [ ] Implement POST endpoints for remote actions
- [ ] Add touch-friendly layout
- [ ] Test on mobile browsers

---

## Backlog

### Epic 1: Core Gesture System
- [ ] Story 1.2: Improve Gesture Reliability
- [ ] Story 1.3: Add Start/Exit Presentation Gestures

### Epic 2: User Customization
- [ ] Story 2.2: Gesture-to-Action Remapping
- [ ] Story 2.3: Sensitivity Profiles

### Epic 3: Dashboard & Remote Control
- [ ] Story 3.2: Enhanced Dashboard UI
- [ ] Story 3.3: Gesture Recording/Playback

### Epic 4: Performance & Reliability
- [ ] Story 4.1: Session Logging
- [ ] Story 4.2: Latency Monitoring
- [ ] Story 4.3: Graceful Error Recovery

### Epic 5: Platform Support
- [ ] Story 5.1: macOS Improvements
- [ ] Story 5.2: Windows Improvements

---

## Completed

### Epic 0: Foundation
- [x] Codebase cleanup
- [x] Test coverage expansion (3 → 54 tests)
- [x] Add requirements.txt
- [x] Fix trigger.py redundant conditional
- [x] Remove dead _is_fist() method

---

## Notes

**Recommended Order:**
1. Per-app bindings (unblocks existing feature, low effort)
2. First/last slide gestures (high user value)
3. Remote control (transforms dashboard utility)
4. Session logging (enables debugging)
5. Gesture remapping (user customization)

**Dependencies:**
- Story 2.1 has no dependencies, can start immediately
- Story 1.1 depends on config.py changes only
- Story 3.1 depends on web/server.py patterns already in place
