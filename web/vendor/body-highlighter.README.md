# [body-highlighter](https://www.npmjs.com/package/body-highlighter)

[![Npm Version][npm-version-image]][npm-version-url]
[![License][license-image]][license-url]
[![Downloads][downloads-image]][downloads-url]

Body Highlighter is a **framework‑agnostic** muscle map that renders straight to the DOM with zero runtime dependencies. It started as a fork of [react-body-highlighter](https://github.com/giavinh79/react-body-highlighter) and is now maintained as a standalone, modern alternative.

## Why this fork?

- ✅ Works in any environment (vanilla JS, React, Vue, Svelte, Astro, …)
- ✅ Accepts **human-readable muscle names** and auto-maps them to the closest `MuscleType`
- ✅ Kept up to date with the latest tooling (TypeScript 5, Husky 9, etc.)
- ✅ Tiny footprint: a single SVG plus a handful of utility helpers

Jump straight to the [example playground](example/) if you want to see it live.

## Installation

```sh
$ npm install body-highlighter
```

```sh
$ yarn add body-highlighter
```

## Usage

**Example**

```ts
import createBodyHighlighter, { IExerciseData, MuscleType } from 'body-highlighter';

const container = document.getElementById('model');

const data: IExerciseData[] = [
  { name: 'Bench Press', muscles: [MuscleType.CHEST, MuscleType.TRICEPS, MuscleType.FRONT_DELTOIDS] },
  { name: 'Push Ups', muscles: [MuscleType.CHEST] },

  // You can mix canonical enums with natural language names.
  { name: 'Extensions lombaires', muscles: ['Erector Spinae'] },
];

const highlighter = createBodyHighlighter({
  container,
  data,
  style: { width: '20rem', padding: '5rem' },
  onClick: ({ muscle, data }) => {
    const { exercises, frequency } = data;

    alert(`You clicked the ${muscle}! You've worked out this muscle ${frequency} time(s) through: ${JSON.stringify(exercises)}`);
  },
});

// Update highlights whenever your data changes
highlighter.update({
  data: [...data, { name: 'Dips', muscles: [MuscleType.TRICEPS] }],
});
```

## Options

All options are optional; if omitted they fall back to the defaults shown below.

| Prop              | Purpose                                                                                                                          | Type                                            | Default                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------ |
| bodyColor         | Default color applied to muscles with no recorded activity                                                                       | `string`                                        | `#B6BDC3`                      |
| container         | Optional container element that will automatically receive the generated markup                                                  | `HTMLElement`                                   |                                |
| data              | Array of exercise objects `{ name: string, muscles: Muscle[], frequency?: number }` used to compute activity stats               | `IExerciseData[]`                               | `[]`                           |
| highlightedColors | Palette used depending on how frequently a muscle was worked (`frequency - 1` = index). The last color is reused for higher reps | `string[]`                                      | `['#81b1d9', '#277abf']`       |
| onClick           | Callback fired when a muscle polygon is clicked. Receives `{ muscle, data: { exercises, frequency } }`                           | `(stats: IMuscleStats) => void`                 |                                |
| style             | Inline styles applied to the wrapper element                                                                                     | `Record<string, string | number | undefined>`   |                                |
| svgStyle          | Inline styles applied directly to the `<svg>`                                                                                    | `Record<string, string | number | undefined>`   |                                |
| type              | Denotes which body view is rendered                                                                                              | `ModelType` (`'anterior'` \| `'posterior'`)     | `'anterior'`                   |
| wrapperClassName  | Class name assigned to the wrapper `div`                                                                                          | `string`                                        | `'rbh-wrapper'`                |

### Instance helpers

`createBodyHighlighter` returns an object containing:

- `element`: the root `HTMLElement` that wraps the SVG. Append it manually when no `container` is supplied.
- `update(options)`: re-computes fills and styles with the provided partial options.
- `destroy()`: removes the element from the DOM and clears internal listeners.

## List of muscles/parts supported

```
/* Back */
trapezius
upper-back
lower-back

/* Chest */
chest

/* Arms */
biceps
triceps
forearm
back-deltoids
front-deltoids

/* Abs */
abs
obliques

/* Legs */
adductor
hamstring
quadriceps
abductors
calves
gluteal

/* Head */
head
neck
```

### Muscle aliases

Common anatomical names such as `Trapezius`, `Pectoralis Major`, or `Gluteus Maximus` are automatically normalised to their closest muscle group (case insensitive). Unknown aliases are simply ignored, so you can still fall back to the canonical keys above when you need full control.


## Modifying

The root wrapper receives the class `.rbh-wrapper` and the SVG uses `.rbh`, so you can style everything with regular CSS. For instance:

```css
.rbh polygon:hover {
  fill: #757782 !important;
}
```

Contributions are welcome—open an issue or PR if you have ideas for new features or muscle mappings!
