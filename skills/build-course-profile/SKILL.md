---
name: build-course-profile
description: Derive and register a reviewed course-specific method and deliverable-style profile from instructor materials, templates, and anonymized examples.
---

Use when a course is first ingested, its deliverable conventions change, or assignments are producing generic formatting. Work only inside the private course workspace. Prefer evidence in this order: current instructor assignment, instructor template, reviewed course guidance, anonymized reviewed student example, then unresolved evidence. Historical syllabus AI-policy sections are excluded when the owner configured that exclusion; they do not control the profile.

Inspect exact source locations before recording a rule. Use `search` to retrieve document IDs, source hashes, locators, and text hashes, then use `evidence-review` after checking the source in context. For visual conventions, inspect the actual pages rather than relying only on extracted text. Record concrete settings such as body size, spacing, margins, title page, abstract, page numbering, caption position, section order, expected length, and level of detail. Keep uncertain or conflicting conventions unresolved. Remove names, IDs, group membership, and prior results from reusable profile data.

Fill `.calvin-autonomy/templates/course-profile.json` with only supported rules and exact reviewed evidence. Preserve the template's authority order. Register it with `.calvin-autonomy/bin/coursework --workspace workspace profile-set PROFILE.json --course COURSE_ID`, then confirm it with `profile-show --course COURSE_ID`. Rebuild the profile when a controlling source changes; assignment plans bind the current profile hash.

This skill creates course-scoped presentation and method guidance. It does not promote one student's writing quirks into professor requirements, infer undocumented grading preferences, or replace the current assignment instructions.
