/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 暖色调配色 - 奶油色 + 暖灰 + 琥珀色强调
        primary: {
          50: '#FFFBEB',  // 最浅奶油
          100: '#FEF3C7', // 浅奶油
          200: '#FDE68A',
          300: '#FCD34D',
          400: '#FBBF24',
          500: '#F59E0B', // 琥珀色
          600: '#D97706', // 主色 - 深琥珀
          700: '#B45309', // 强调色
          800: '#92400E',
          900: '#78350F', // 深棕色
          950: '#451A03',
        },
        // 功能色 - 股票涨跌（保持清晰可辨）
        profit: {
          DEFAULT: '#059669', // 深翠绿（在暖色背景上更清晰）
          light: 'rgba(5, 150, 105, 0.15)',
          dark: 'rgba(5, 150, 105, 0.1)',
        },
        loss: {
          DEFAULT: '#DC2626', // 鲜红
          light: 'rgba(220, 38, 38, 0.15)',
          dark: 'rgba(220, 38, 38, 0.1)',
        },
        warning: {
          DEFAULT: '#D97706', // 琥珀
          light: 'rgba(217, 119, 6, 0.15)',
        },
        info: {
          DEFAULT: '#4F46E5', // 靛蓝
          light: 'rgba(79, 70, 229, 0.15)',
        },
        // 暖色背景系统
        warm: {
          50: '#FFFBEB',   // 主背景 - 奶油色
          100: '#FEF3C7',  // 次要背景
          200: '#FDE68A',  // 浅黄
          300: '#FCD34D',
          400: '#FBBF24',
          500: '#F59E0B',  // 琥珀
          600: '#D97706',
          700: '#B45309',
          800: '#92400E',
          900: '#78350F',  // 深棕
        },
        // 暖灰色系
        warmgray: {
          50: '#FAFAF9',   // 卡片背景
          100: '#F5F5F4',
          200: '#E7E5E4',  // 边框
          300: '#D6D3D1',
          400: '#A8A29E',  // 次要文字
          500: '#78716C',  // 弱化文字
          600: '#57534E',
          700: '#44403C',  // 次要深色
          800: '#292524',  // 主文字
          900: '#1C1917',  // 最深
        },
        // 暗色背景（用于对比区域）
        dark: {
          900: '#1C1917',
          800: '#292524',
          700: '#44403C',
          600: '#57534E',
          500: '#78716C',
          400: '#A8A29E',
          300: '#D6D3D1',
          200: '#E7E5E4',
          100: '#F5F5F4',
          50: '#FAFAF9',
        },
        // 边框色
        border: {
          DEFAULT: '#E7E5E4', // warmgray-200
          light: '#F5F5F4',   // warmgray-100
          strong: '#D6D3D1',  // warmgray-300
        },
        // CTA 色
        cta: {
          DEFAULT: '#D97706', // primary-600 琥珀
          hover: '#B45309',   // primary-700
          light: 'rgba(217, 119, 6, 0.15)',
        },
      },
      fontFamily: {
        // 使用温暖的圆角字体
        sans: ['Nunito Sans', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['Fira Code', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': ['11px', { lineHeight: '1.4' }],
        'data': ['14px', { lineHeight: '1', fontWeight: '500' }],
        'data-lg': ['18px', { lineHeight: '1', fontWeight: '600' }],
        'kpi': ['24px', { lineHeight: '1.2', fontWeight: '700' }],
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      boxShadow: {
        'soft': '0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'card': '0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'hover': '0 4px 12px 0 rgba(0, 0, 0, 0.08), 0 2px 4px 0 rgba(0, 0, 0, 0.04)',
        'glow-green': '0 0 10px rgba(5, 150, 105, 0.2)',
        'glow-red': '0 0 10px rgba(220, 38, 38, 0.2)',
      },
      borderRadius: {
        'sm': '4px',
        'md': '6px',
        'lg': '8px',
        'xl': '12px',
      },
      backdropBlur: {
        'xs': '2px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'data-update': 'dataUpdate 1s ease-out',
        'flash-green': 'flashGreen 0.5s ease-out',
        'flash-red': 'flashRed 0.5s ease-out',
      },
      keyframes: {
        dataUpdate: {
          '0%': { backgroundColor: 'rgba(217, 119, 6, 0.2)' },
          '100%': { backgroundColor: 'transparent' },
        },
        flashGreen: {
          '0%': { backgroundColor: 'rgba(5, 150, 105, 0.3)' },
          '100%': { backgroundColor: 'transparent' },
        },
        flashRed: {
          '0%': { backgroundColor: 'rgba(220, 38, 38, 0.3)' },
          '100%': { backgroundColor: 'transparent' },
        },
      },
      transitionDuration: {
        '150': '150ms',
        '200': '200ms',
        '300': '300ms',
      },
    },
  },
  plugins: [],
}

