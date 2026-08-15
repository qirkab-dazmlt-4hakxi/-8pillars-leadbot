# GOAT Award-to-Execution Operating Core

This layer closes the operational loop between winning work and protecting
profit during execution.

## Award handoff

The awarded estimate becomes a controlled project baseline containing:

- estimate identity
- proposal hash
- original contract value
- project identity
- awarded budget by cost code
- original budget by category

The estimate/proposal provenance remains attached to the project.

## Project budget

GOAT distinguishes:

- original budget
- approved change budget
- budget transfers
- current budget

Budget transfers preserve the total project budget.

Approved change cost increases the applicable execution budget.

## Commitments

GOAT models:

- purchase orders
- subcontracts
- rentals
- service agreements
- other commitments

Each commitment tracks:

- original amount
- approved changes
- invoiced amount
- remaining commitment
- lifecycle status

This allows the forecast to distinguish incurred cost from committed future
cost.

## Actual cost

Actual cost remains tied to:

- project
- cost code
- cost category
- transaction date
- source reference
- optional commitment

All currency is integer cents.

Floating point values are not used for authoritative currency.

## Field production

Daily logs capture:

- labor hours
- equipment hours
- installed quantities
- unit
- cost code
- production constraints
- safety notes
- weather summary

Productivity intelligence compares planned labor-hours-per-unit with
actual labor consumption.

## Progress and earned value

GOAT stores:

- actual percent complete
- planned percent complete
- earned value
- planned value
- CPI
- SPI

Progress is weighted by current cost-code budget.

Actual progress cannot silently move backward.

## Material releases

Material control includes:

- planned releases
- ordered material
- partial delivery
- completed delivery
- required-on-site dates
- vendor assignment

Executive intelligence identifies material that should already be on site
but remains undelivered.

## Change management

Change events track:

- estimated cost exposure
- requested price
- approved cost
- approved price
- schedule impact
- at-risk execution
- source reference
- status

GOAT differentiates approved contract value from unapproved exposure.

At-risk work is surfaced as an executive intervention instead of being
silently absorbed into project cost.

## Forecasting

GOAT produces cost-code and project forecasts including:

- current budget
- actual cost
- open commitments
- ETC
- EAC
- variance at completion
- earned value
- planned value
- CPI
- SPI
- original contract
- current contract
- gross-profit forecast
- gross-margin forecast
- margin erosion

Where enough progress evidence exists, performance EAC can extrapolate
actual cost against physical progress.

Authorized management may explicitly override ETC with an audited reason.

## Billing and WIP

The operating core calculates:

- gross billing
- retainage
- collections
- accounts receivable
- earned revenue
- overbilling
- underbilling

These values support project-level WIP and cash-risk intelligence.

## Executive intervention intelligence

GOAT automatically surfaces deterministic intervention signals for:

- negative projected gross profit
- material margin erosion
- low CPI
- low SPI
- unapproved change exposure
- work executed at risk
- overcommitted cost codes
- poor field productivity
- late material
- missing/stale daily logs
- material accounts-receivable exposure

These are management signals, not autonomous financial decisions.

## Audit integrity

Every project-domain mutation creates a chained audit event.

Each event contains:

- sequence
- event ID
- event type
- actor
- timestamp
- payload hash
- previous-event hash
- current-event hash

Tampering with an audit payload or chain is detectable.

## Durable data spine

The execution domain can publish its verified audit events into GOAT's
existing durable event store and transactional outbox.

Production service orchestration should ensure authoritative mutations pass
through GOAT's durable transaction boundary.

## Next integration

The next major layer should connect this operating core to:

- employee/crew scheduling
- timecards
- payroll-cost burden
- equipment telematics
- superintendent command center
- QA/QC inspections
- punch lists
- RFIs/submittals
- project document control
- client portal
- owner/GC billing workflows
- payment applications
- lien-waiver tracking
- subcontractor compliance
- safety documentation
- mobile field workflows
