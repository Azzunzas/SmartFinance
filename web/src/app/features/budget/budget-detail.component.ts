import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, effect, inject, input, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import {
  AbstractControl,
  FormArray,
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  ValidationErrors,
  Validators
} from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { PlannedItemsService } from '../../core/api/generated/planned-items/planned-items.service';
import {
  MatchType,
  PlannedItemRuleCreate,
  PlannedItemRuleOut,
  RulePreviewResponse
} from '../../core/api/generated/smartFinanceAPI.schemas';
import { MatchTypeLabelPipe } from '../../shared/pipes/match-type-label.pipe';
import { PlannedKindLabelPipe } from '../../shared/pipes/planned-kind-label.pipe';

interface RuleControls {
  id: FormControl<number | null>;
  match_type: FormControl<MatchType>;
  pattern: FormControl<string | null>;
  amount_min: FormControl<number | null>;
  amount_max: FormControl<number | null>;
  account_id: FormControl<number | null>;
  priority: FormControl<number>;
}

// Validador de grupo, mesma ideia do `model_validator(mode="after")` do
// Pydantic no backend: roda depois que os campos individuais já validaram,
// porque depende de dois campos ao mesmo tempo.
function amountRangeValidator(control: AbstractControl): ValidationErrors | null {
  const group = control as FormGroup<RuleControls>;
  const min = group.controls.amount_min.value;
  const max = group.controls.amount_max.value;
  if (min != null && max != null && min > max) {
    return { amountRange: true };
  }
  return null;
}

function createRuleGroup(initial?: PlannedItemRuleOut): FormGroup<RuleControls> {
  return new FormGroup<RuleControls>(
    {
      id: new FormControl(initial?.id ?? null),
      match_type: new FormControl(initial?.match_type ?? 'CONTAINS', {
        nonNullable: true,
        validators: Validators.required
      }),
      pattern: new FormControl(initial?.pattern ?? null),
      amount_min: new FormControl(initial?.amount_min != null ? Number(initial.amount_min) : null),
      amount_max: new FormControl(initial?.amount_max != null ? Number(initial.amount_max) : null),
      account_id: new FormControl(initial?.account_id ?? null),
      priority: new FormControl(initial?.priority ?? 100, { nonNullable: true })
    },
    { validators: amountRangeValidator }
  );
}

type PreviewState = RulePreviewResponse | 'error';

@Component({
  selector: 'app-budget-detail',
  imports: [
    ReactiveFormsModule,
    CurrencyPipe,
    DatePipe,
    RouterLink,
    PlannedKindLabelPipe,
    MatchTypeLabelPipe
  ],
  templateUrl: './budget-detail.component.html',
  styleUrl: './budget-detail.component.css'
})
export class BudgetDetailComponent {
  readonly id = input.required<string>();

  private readonly plannedItemsService = inject(PlannedItemsService);
  private readonly router = inject(Router);

  protected readonly matchTypes = Object.values(MatchType);
  protected readonly previewResults = signal<Record<number, PreviewState>>({});

  protected readonly item = rxResource({
    params: () => this.id(),
    stream: ({ params }) =>
      this.plannedItemsService.getItemApiPlannedItemsPlannedItemIdGet(Number(params))
  });

  private readonly rulesResource = rxResource({
    params: () => this.id(),
    stream: ({ params }) =>
      this.plannedItemsService.listItemRulesApiPlannedItemsPlannedItemIdRulesGet(Number(params))
  });

  protected readonly rules = new FormArray<FormGroup<RuleControls>>([]);

  constructor() {
    // FormArray é estado imperativo (push/removeAt), não um signal puro — por
    // isso precisa de um effect pra sincronizar com o resultado do resource
    // toda vez que ele recarregar.
    effect(() => {
      const loadedRules = this.rulesResource.value();
      if (loadedRules) {
        this.rules.clear();
        for (const rule of loadedRules) {
          this.rules.push(createRuleGroup(rule));
        }
      }
    });
  }

  addRule(): void {
    this.rules.push(createRuleGroup());
  }

  deleteItem(): void {
    if (!confirm('Apagar este item de orçamento? Essa ação não pode ser desfeita.')) {
      return;
    }
    this.plannedItemsService
      .removeItemApiPlannedItemsPlannedItemIdDelete(Number(this.id()))
      .subscribe(() => this.router.navigate(['/budget']));
  }

  previewRule(index: number): void {
    const group = this.rules.at(index);
    if (group.invalid) {
      group.markAllAsTouched();
      return;
    }
    const value = group.getRawValue();
    this.plannedItemsService
      .previewRuleApiPlannedItemsPlannedItemIdRulesPreviewPost(Number(this.id()), {
        match_type: value.match_type,
        pattern: value.pattern,
        amount_min: value.amount_min,
        amount_max: value.amount_max,
        account_id: value.account_id
      })
      .subscribe({
        next: (result) => this.previewResults.update((map) => ({ ...map, [index]: result })),
        error: () => this.previewResults.update((map) => ({ ...map, [index]: 'error' }))
      });
  }

  saveRule(index: number): void {
    const group = this.rules.at(index);
    if (group.invalid) {
      group.markAllAsTouched();
      return;
    }
    const value = group.getRawValue();
    const payload: PlannedItemRuleCreate = {
      match_type: value.match_type,
      pattern: value.pattern,
      amount_min: value.amount_min,
      amount_max: value.amount_max,
      account_id: value.account_id,
      priority: value.priority
    };

    if (value.id == null) {
      this.plannedItemsService
        .createItemRuleApiPlannedItemsPlannedItemIdRulesPost(Number(this.id()), payload)
        .subscribe((created) => group.controls.id.setValue(created.id));
    } else {
      this.plannedItemsService
        .patchItemRuleApiPlannedItemsPlannedItemIdRulesRuleIdPatch(
          Number(this.id()),
          value.id,
          payload
        )
        .subscribe();
    }
  }

  removeRule(index: number): void {
    const group = this.rules.at(index);
    const ruleId = group.controls.id.value;
    if (ruleId == null) {
      this.rules.removeAt(index);
      return;
    }
    this.plannedItemsService
      .removeItemRuleApiPlannedItemsPlannedItemIdRulesRuleIdDelete(Number(this.id()), ruleId)
      .subscribe(() => this.rules.removeAt(index));
  }
}
