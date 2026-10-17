import { CurrencyPipe } from '@angular/common';
import { Component, inject, input, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { RecurrencesService } from '../../core/api/generated/recurrences/recurrences.service';
import { DirectionLabelPipe } from '../../shared/pipes/direction-label.pipe';

@Component({
  selector: 'app-recurrence-promote',
  imports: [ReactiveFormsModule, CurrencyPipe, RouterLink, DirectionLabelPipe],
  templateUrl: './recurrence-promote.component.html',
  styleUrl: './recurrence-promote.component.css',
})
export class RecurrencePromoteComponent {
  readonly id = input.required<string>();

  private readonly fb = inject(FormBuilder);
  private readonly recurrencesService = inject(RecurrencesService);
  private readonly router = inject(Router);

  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);

  protected readonly candidate = rxResource({
    stream: () =>
      this.recurrencesService.getCandidateApiRecurrencesCandidateIdGet(Number(this.id())),
  });

  protected readonly form = this.fb.group({
    name: this.fb.control('', { nonNullable: true, validators: Validators.required }),
    valid_from: this.fb.control('', { nonNullable: true, validators: Validators.required }),
    tolerance_pct: this.fb.control(10, { nonNullable: true }),
    expected_day: this.fb.control<number | null>(null),
    day_tolerance: this.fb.control(5, { nonNullable: true }),
  });

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    this.saving.set(true);
    this.errorMessage.set(null);

    this.recurrencesService
      .promoteCandidateApiRecurrencesCandidateIdPromotePost(Number(this.id()), {
        name: value.name,
        valid_from: value.valid_from,
        tolerance_pct: value.tolerance_pct,
        expected_day: value.expected_day,
        day_tolerance: value.day_tolerance,
      })
      .subscribe({
        next: (created) => this.router.navigate(['/budget', created.id]),
        error: () => {
          this.saving.set(false);
          this.errorMessage.set('Não foi possível promover. Confira os campos e tente de novo.');
        },
      });
  }
}
