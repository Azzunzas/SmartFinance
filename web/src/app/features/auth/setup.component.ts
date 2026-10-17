import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthSessionService } from '../../core/auth/auth-session.service';

@Component({
  selector: 'app-setup',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './setup.component.html',
  styleUrl: './auth.css',
})
export class SetupComponent {
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly session = inject(AuthSessionService);

  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly alreadyConfigured = signal(false);
  protected readonly form = this.fb.group({
    username: this.fb.control('', { nonNullable: true, validators: Validators.required }),
    password: this.fb.control('', {
      nonNullable: true,
      validators: [Validators.required, Validators.minLength(8)],
    }),
  });

  protected submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);
    this.alreadyConfigured.set(false);
    this.session.register(this.form.getRawValue()).subscribe({
      next: () => void this.router.navigateByUrl('/overview'),
      error: (error: unknown) => {
        this.submitting.set(false);
        if (error instanceof HttpErrorResponse && error.status === 409) {
          this.alreadyConfigured.set(true);
          this.errorMessage.set(
            'Este SmartFinance já foi configurado. Entre com o acesso existente.',
          );
          return;
        }
        this.errorMessage.set('Não foi possível criar o acesso. Tente novamente.');
      },
    });
  }
}
