# GOAT Field Operations Command Core

This subsystem connects field execution directly to GOAT project,
financial and executive intelligence.

## Workforce

GOAT tracks:

- employees
- employee numbers
- roles
- hourly rates
- payroll burden
- benefits burden
- workers compensation burden
- supervision burden
- certifications
- crew membership
- foreman assignment
- project/cost-code crew assignment

## Timecards

Timecards support:

- regular hours
- overtime
- doubletime
- workflow status
- project
- cost code
- burdened labor cost

Approved timecards can post directly into GOAT job cost using idempotent
execution transactions.

## Equipment

GOAT tracks:

- equipment assets
- asset number
- internal hourly cost
- assignment
- utilization
- meter hours
- operator
- project
- cost code

Equipment usage can post to execution job cost.

## QA/QC

Inspections support:

- inspection type
- drawing references
- specification references
- inspection checklist items
- pass
- pass with notes
- fail
- hold
- corrective action
- closeout

Failed and hold inspections require documented corrective action.

## Safety documentation

GOAT records project-specific Job Safety Analyses including:

- activity
- hazards
- controls
- severity
- crew
- attendees
- acknowledgment

This software records and surfaces safety documentation.

It does not replace project-specific competent-person judgment,
professional engineering, adopted safety regulations, employer programs
or legally required training.

## RFIs

GOAT tracks:

- automatic project RFI numbering
- subject
- question
- drawing references
- specification references
- cost code
- assignee
- due date
- response
- responder
- timestamps
- lifecycle status

Overdue RFIs automatically surface in field command intelligence.

## Submittals

GOAT tracks:

- automatic numbering
- specification section
- supplier
- required-on-site date
- revisions
- submission date
- return date
- review status
- review notes

Late submittal cycles surface as execution risks.

## Punch lists

Punch items include:

- location
- description
- assignee
- due date
- photos
- workflow status
- closeout timestamp

## Subcontractor compliance

Compliance records support:

- insurance
- W-9
- subcontract/agreement
- safety documentation
- expiration dates
- compliance status

Expired documentation prevents the subcontractor from being classified
as compliant.

## Lien waivers

GOAT supports:

- conditional progress
- unconditional progress
- conditional final
- unconditional final

Waiver amount, through-date, signature status and reference are retained.

Legal enforceability and required statutory waiver language remain
jurisdiction-specific and should be reviewed against current applicable law.

## Pay applications

Subcontractor pay applications track:

- gross request
- retainage
- net request
- approved amount
- paid amount
- lien-waiver linkage
- compliance gate
- status

Payment approval is blocked when the subcontractor fails the configured
compliance gate.

## Mobile synchronization

GOAT's mobile synchronization architecture uses version-based optimistic
concurrency.

Clients can create/update/delete local records while offline.

When the device reconnects:

- matching base version is accepted
- server version increments
- stale mutation is rejected as conflict
- newer server state is preserved

This supports iPhone, iPad, Android, Windows and browser field clients
without silent last-write-wins data destruction.

## Superintendent command center

Field risk intelligence automatically evaluates:

- overdue RFIs
- late submittals
- failed/hold QAQC inspections
- subcontractor compliance
- unacknowledged critical JSA records
- elevated overtime

The field health score is deterministic and evidence-based.

## Execution bridge

Approved timecards and equipment usage post to GOAT's existing
award-to-execution job cost system.

This links:

field activity
→ labor/equipment cost
→ project EAC
→ margin forecast
→ executive intelligence

The result is a closed operational feedback loop rather than disconnected
field and accounting systems.
