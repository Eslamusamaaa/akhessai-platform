# Final report results

What the specialist sees after a full parent → teacher → specialist cycle and
`POST /sessions/{id}/generate-report` runs: the deterministic severity scores
plus the AI-drafted clinical report, all on one editable page before approval.

This was captured from a real run against the live deployment (synthetic
"طفل تجريبي" test case, autism specialty) — not a mockup. The screenshots
themselves still need to be added (see note at the bottom); what follows is
the actual content that run produced.

## Objective scoring (rule engine, no LLM involved)

| Domain | Anxiety score | Severity |
|---|---|---|
| التواصل الاجتماعي (social communication) | 55.7 / 100 | متوسط (L3) |
| الانتباه والتركيز (attention) | 50.0 / 100 | متوسط (L3) |
| اللغة الاستقبالية (receptive language) | 46.7 / 100 | متوسط (L3) |
| الاستجابة الحسية (sensory response) | 33.3 / 100 | خفيف (L2) |
| التنظيم الانفعالي (emotional regulation) | 53.3 / 100 | متوسط (L3) |
| المهارات الأكاديمية (academic skills) | 50.0 / 100 | متوسط (L3) |
| السلوكيات النمطية التكرارية (restricted/repetitive) | 56.6 / 100 | متوسط (L3) |
| اللغة التعبيرية (expressive language) | 54.3 / 100 | متوسط (L3) |
| اللغة البراغماتية الاجتماعية (pragmatic language) | 75.0 / 100 | **شديد (L4)** |
| النطق ومخارج الحروف (articulation) | 52.0 / 100 | متوسط (L3) |

**Priority tier:** Priority 2 — تقييم أخصائي موصى به.
**Cross-informant flag:** 26.6-point gap between parent and teacher on emotional
regulation — the evaluator explicitly recommends gathering more information
rather than guessing.

## AI-drafted report (after RAG + LLM, before specialist edits)

The draft included, as structured JSON rendered into the editable form:
- **Differential-diagnosis note** — distinguishing autism-driven language delay
  (impaired nonverbal communication, absent imaginative play, stereotyped
  behaviors) from pure language delay (relatively intact social communication).
- **5 SMART goals** — e.g. "initiate a conversation with a peer using an
  appropriate opener, 3 times a week" — each tied to a specific domain.
- **Intervention plan by specialty** — speech therapy (3 items) and
  occupational therapy (2 items), each item a concrete clinical action.
- **4 school accommodation suggestions** and **3 home-program suggestions**.
- **3 specialty referrals** (psychology/psychiatry for autism assessment,
  psychology for emotional regulation, OT for sensory processing).
- **Follow-up goals** (6-month re-assessment) and **caveats** (explicitly
  flags missing family/developmental-history context).

Every section above is editable inline by the specialist before approval —
see [`pages/ClinicianPortal.tsx`](../../../frontend/src/pages/ClinicianPortal.tsx).

## Adding the actual screenshots

1. Log in to the [live platform](https://frontend-rust-rho-unmixly180.vercel.app)
   with a specialist account (see the main [README](../../../README.md#live-deployment)
   for how to get one).
2. Open a case whose status is "مراجعة المسودة" (draft review) — or run the
   demo flow yourself end to end.
3. Screenshot the clinical observation form, the severity-scores grid, and the
   AI-drafted report sections.
4. Drop the images in this folder and link them from this file, the same way
   [`admin-flow/README.md`](../admin-flow/README.md) does.
