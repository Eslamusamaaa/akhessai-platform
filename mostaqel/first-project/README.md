# Project 1 - Akhessai assessment walkthrough

Screenshots of one complete case, captured from a **local run with fictional test data**: parent questionnaire, teacher questionnaire, clinician observation and the rule-engine results.

### Parent dashboard: register a new child
![Parent dashboard: register a new child](01-register-child-form.jpg)

### Registration form (fictional test data) with the screening specialties selected
![Registration form (fictional test data) with the screening specialties selected](02-register-child-filled.jpg)

### Case created; the parent's progress tracker (step 2 of 6)
![Case created; the parent's progress tracker (step 2 of 6)](03-parent-dashboard-child-registered.jpg)

### Parent questionnaire: single-choice question (Arabic, RTL)
![Parent questionnaire: single-choice question (Arabic, RTL)](04-parent-question-single-choice.jpg)

### Parent questionnaire: 1-5 rating scale
![Parent questionnaire: 1-5 rating scale](05-parent-question-rating-scale.jpg)

### Answer selected before saving and continuing
![Answer selected before saving and continuing](06-parent-question-answer-selected.jpg)

### Adaptive follow-up question (speech and language)
![Adaptive follow-up question (speech and language)](07-parent-question-language.jpg)

### Parent view after finishing: waiting for the teacher
![Parent view after finishing: waiting for the teacher](08-parent-dashboard-waiting-for-teacher.jpg)

### Teacher questionnaire (school-environment items)
![Teacher questionnaire (school-environment items)](09-teacher-question.jpg)

### Teacher questionnaire: social interaction question
![Teacher questionnaire: social interaction question](10-teacher-question-social.jpg)

### Teacher dashboard: case moves on to the clinician
![Teacher dashboard: case moves on to the clinician](11-teacher-dashboard-awaiting-clinical-observation.jpg)

### Specialist dashboard: case awaiting clinical observation
![Specialist dashboard: case awaiting clinical observation](12-specialist-dashboard.jpg)

### Clinical observation form (1-5 scales)
![Clinical observation form (1-5 scales)](13-clinical-observation-form.jpg)

### Observation notes and submit
![Observation notes and submit](14-clinical-observation-submit.jpg)

### Results: severity level and anxiety index per domain from the deterministic rule engine
![Results: severity level and anxiety index per domain from the deterministic rule engine](15-results-domain-severity-scores.jpg)

### Results: overall priority tier and parent/teacher discrepancy flags
![Results: overall priority tier and parent/teacher discrepancy flags](16-results-priority-tier-and-informant-gaps.jpg)

> The AI-written narrative section of the report needs an `OPENROUTER_API_KEY`; it was not configured for these screenshots, so only the deterministic scoring and flags are shown.
