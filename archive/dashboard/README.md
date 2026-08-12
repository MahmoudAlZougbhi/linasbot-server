# 🤖 Lina's Laser AI Dashboard

A stunning, modern React dashboard for managing your WhatsApp AI bot. Built with cutting-edge design and smooth animations.

## ✨ Features

### 🧪 **Testing Laboratory**

- **Text Testing**: Multi-language message testing with real-time responses
- **Voice Testing**: Upload audio files for transcription testing
- **Image Testing**: Upload images for AI analysis testing
- **Language Detection**: Automatic language detection and appropriate responses

### 🎓 **AI Training Center**

- **Smart Training**: Add Q&A pairs with AI-powered answer rewriting
- **Knowledge Management**: View, edit, and delete training data
- **Similarity Search**: Test similarity matching with 90% threshold logic
- **Multi-language Support**: Train in Arabic, English, French, and Franco-Arabic

### 📊 **Dashboard Overview**

- **Real-time Stats**: Bot performance metrics and system status
- **Quick Actions**: Easy access to testing and training features
- **System Monitoring**: Live status of all bot components
- **Recent Activity**: Track all bot interactions and tests

### ⚙️ **Settings & Configuration**

- **General Settings**: Bot name, language preferences, timeouts
- **API Management**: Monitor and test all API connections
- **Language Configuration**: Enable/disable supported languages
- **Notification Settings**: Customize alerts and notifications

### 🎨 **Modern Design**

- **Glass Morphism**: Beautiful frosted glass effects
- **Smooth Animations**: Framer Motion powered transitions
- **Responsive Design**: Perfect on desktop, tablet, and mobile
- **Dark/Light Themes**: Automatic theme adaptation
- **Gradient Accents**: Stunning color gradients throughout

## 🚀 Quick Start

### Prerequisites

- Node.js 16+ installed
- Your bot backend running on port 8001

### Installation

1. **Navigate to dashboard directory:**

   ```bash
   cd dashboard
   ```

2. **Install dependencies:**

   ```bash
   npm install
   ```

3. **Start development server:**

   ```bash
   npm start
   ```

4. **Open your browser:**
   ```
   http://localhost:3000
   ```

### Production Build

```bash
npm run build
```

## 🏗️ Architecture

### Component Structure

```
src/
├── components/
│   ├── Layout/
│   │   ├── Sidebar.js      # Navigation sidebar
│   │   └── Header.js       # Top header bar
│   └── Common/
│       └── LoadingScreen.js # Beautiful loading animation
├── pages/
│   ├── Dashboard.js        # Main overview page
│   ├── Testing.js          # Testing laboratory
│   ├── Training.js         # AI training center
│   ├── LiveChat.js         # Live chat monitor (coming soon)
│   ├── Analytics.js        # Analytics dashboard (coming soon)
│   └── Settings.js         # Settings & configuration
├── hooks/
│   └── useApi.js          # API integration hook
└── styles/
    └── index.css          # Tailwind CSS with custom styles
```

### Design System

#### Colors

- **Primary**: Purple gradient (`#d946ef` to `#c026d3`)
- **Secondary**: Blue gradient (`#0ea5e9` to `#0284c7`)
- **Accent**: Yellow gradient (`#eab308` to `#ca8a04`)
- **Glass**: Semi-transparent white with backdrop blur

#### Typography

- **Display Font**: Poppins (headings)
- **Body Font**: Inter (body text)
- **Weights**: 300, 400, 500, 600, 700, 800

#### Animations

- **Page Transitions**: Smooth fade and slide effects
- **Hover Effects**: Scale and glow transformations
- **Loading States**: Elegant spinner and skeleton screens
- **Tab Switching**: Fluid layout animations

## 🔌 API Integration

The dashboard connects to your bot backend via the `useApi` hook:

### Endpoints Used

- `GET /api/test` - Bot status and health check
- `POST /api/test-text` - Text message testing
- `POST /api/test-voice` - Voice transcription testing
- `POST /api/test-image` - Image analysis testing
- `POST /api/training/add` - Add training data
- `GET /api/training/list` - Get training data
- `DELETE /api/training/:id` - Delete training entry

### Configuration

The API base URL is automatically configured:

- **Development**: `http://localhost:8001`
- **Production**: `https://bot.tradershubs.site`

## 🎯 Current Status

### ✅ **Active Features**

- **Testing Lab**: Fully functional for text, voice, and image testing
- **Training Center**: Complete Q&A management system
- **Dashboard**: Real-time stats and system monitoring
- **Settings**: Full configuration management

### 🔄 **Coming Soon** (Production Ready)

- **Live Chat Monitor**: Real-time conversation monitoring
- **Analytics Dashboard**: Comprehensive performance metrics
- **Customer Profiles**: User management and history
- **Advanced Reporting**: Export and analysis tools

## 🛠️ Development

### Available Scripts

- `npm start` / `npm run dev` - Start the Vite development server
- `npm run build` - Build for production (outputs to `build/`)
- `npm run preview` - Preview the production build locally
- `npm test` - Run the Vitest test suite
- `npm run lint` - Lint the codebase with ESLint

### Customization

#### Adding New Pages

1. Create component in `src/pages/`
2. Add route in `src/App.js`
3. Update navigation in `src/components/Layout/Sidebar.js`

#### Styling

- Uses Tailwind CSS with custom utilities
- Glass morphism effects via custom CSS classes
- Responsive design with mobile-first approach

#### API Integration

- Extend `src/hooks/useApi.js` for new endpoints
- Add error handling and loading states
- Use React Hot Toast for notifications

## 🎨 Design Philosophy

This dashboard embodies modern web design principles:

### **Glass Morphism**

- Semi-transparent backgrounds with backdrop blur
- Subtle borders and shadows for depth
- Layered visual hierarchy

### **Micro-Interactions**

- Hover effects that provide immediate feedback
- Smooth transitions between states
- Loading animations that feel natural

### **Accessibility**

- High contrast ratios for readability
- Keyboard navigation support
- Screen reader friendly markup

### **Performance**

- Lazy loading for optimal bundle size
- Optimized animations with hardware acceleration
- Efficient re-rendering with React best practices

## 📱 Responsive Design

The dashboard is fully responsive across all devices:

- **Desktop**: Full sidebar navigation with expanded content
- **Tablet**: Collapsible sidebar with touch-friendly interactions
- **Mobile**: Bottom navigation with optimized layouts

## 🔒 Security

- API keys are never exposed in frontend code
- Secure token handling for authentication
- Input validation and sanitization
- HTTPS enforcement in production

## 🚀 Deployment

### Development

```bash
npm start
```

### Production

```bash
npm run build
# Serve the build folder with your preferred web server
```

### Docker (Optional)

```dockerfile
FROM node:16-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

## 🎉 Congratulations!

You now have a world-class AI bot dashboard that rivals the best SaaS platforms. The combination of beautiful design, smooth animations, and powerful functionality creates an exceptional user experience.

**Ready to make your clients amazed?** 🚀

---

_Built with ❤️ using React, Tailwind CSS, Framer Motion, and modern web technologies._
