import { Component, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { PlannedItemsService } from '../../core/api/generated/planned-items/planned-items.service';
import { PlannedItemOut, PlannedKind } from '../../core/api/generated/smartFinanceAPI.schemas';
import { PlannedKindLabelPipe } from '../../shared/pipes/planned-kind-label.pipe';

@Component({
  selector: 'app-budget-create',
  imports: [ReactiveFormsModule, PlannedKindLabelPipe],
  templateUrl: './budget-create.component.html',
  styleUrl: './budget-create.component.css'
})
export class BudgetCreateComponent {
  private readonly fb = inject(FormBuilder);
  private readonly plannedItemsService = inject(PlannedItemsService);
  private readonly router = inject(Router);

  protected readonly kinds = Object.values(PlannedKind);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  readonly modal = input(false);
  readonly cancelled = output<void>();
  readonly created = output<PlannedItemOut>();

  protected readonly form = this.fb.group({
    name: this.fb.control('', { nonNullable: true, validators: Validators.required }),
    kind: this.fb.control<PlannedKind>('FIXED_EXPENSE', {
      nonNullable: true,
      validators: Validators.required
    }),
    expected_amount: this.fb.control<number | null>(null, [
      Validators.required,
      Validators.min(0)
    ]),
    tolerance_pct: this.fb.control(10, { nonNullable: true }),
    expected_day: this.fb.control<number | null>(null),
    day_tolerance: this.fb.control(5, { nonNullable: true }),
    valid_from: this.fb.control('', { nonNullable: true, validators: Validators.required }),
    valid_to: this.fb.control<string | null>(null)
  });

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    this.saving.set(true);
    this.errorMessage.set(null);

    this.plannedItemsService
      .createItemApiPlannedItemsPost({
        name: value.name,
        kind: value.kind,
        // required+min(0) já garantidos pelo `if (this.form.invalid) return` acima
        expected_amount: value.expected_amount!,
        tolerance_pct: value.tolerance_pct,
        expected_day: value.expected_day,
        day_tolerance: value.day_tolerance,
        valid_from: value.valid_from,
        valid_to: value.valid_to
      })
      .subscribe({
        next: (created) => {
          if (this.modal()) {
            this.saving.set(false);
            this.created.emit(created);
            return;
          }

          this.router.navigate(['/budget', created.id]);
        },
        error: () => {
          this.saving.set(false);
          this.errorMessage.set('Não foi possível salvar. Confira os campos e tente de novo.');
        }
      });
  }
}
