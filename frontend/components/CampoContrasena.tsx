"use client";

import { useState, type InputHTMLAttributes } from "react";
import { etiquetaVerContrasena, tipoCampoContrasena } from "../lib/contrasena";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function CampoContrasena({ className = "", ...resto }: Props) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative">
      <input
        {...resto}
        type={tipoCampoContrasena(visible)}
        className={`${className} pr-10`}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={etiquetaVerContrasena(visible)}
        aria-pressed={visible}
        className={`absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-macacha-blue ${
          visible ? "text-macacha-blue" : "text-gray-400 hover:text-gray-600"
        }`}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>
    </div>
  );
}
